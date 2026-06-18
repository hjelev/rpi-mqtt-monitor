"""Interactive TUI configurator for rpi-mqtt-monitor.

Launched via `rpi-mqtt-monitor --config`. Lists every setting from
config.py.example (the always-present, richly commented schema source), merges
in the user's current values from config.py, and lets you move through them with
the arrow keys, read each setting's explanation and default, edit scalar values
(bool/int/string) in place, and save back to config.py without disturbing
comments, ordering or formatting.

Complex settings (lists, dicts, the output function) are shown read-only with a
note to edit them directly in config.py.
"""

import curses
import os
import re

# Matches a top-level `key = value` assignment (no leading indentation, so we
# never pick up assignments inside a function body), capturing the `key = `
# prefix, the value, and any trailing inline comment.
ASSIGN_RE = re.compile(r'^(?P<prefix>(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*)'
                       r'(?P<value>.*?)(?P<comment>\s*#.*)?$')

# Same, but for a commented-out example assignment like `# used_space_paths = [`.
COMMENTED_ASSIGN_RE = re.compile(r'^#\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*\S')

# Settings that exist in the file but should not be user-editable here.
HIDDEN_KEYS = {'version'}


class Setting:
    def __init__(self, key, value_text, type_, help_text, section, default_text):
        self.key = key
        self.value_text = value_text      # current value as it will be written
        self.original_text = value_text   # value as loaded; used to detect edits
        self.type = type_                 # 'bool' | 'int' | 'str' | 'complex'
        self.help = help_text
        self.section = section
        self.default_text = default_text


def _infer_type(value_text):
    v = value_text.strip()
    if v in ('True', 'False'):
        return 'bool'
    if re.fullmatch(r'-?\d+', v):
        return 'int'
    if (len(v) >= 2 and v[0] in '"\'' and v[-1] == v[0]):
        return 'str'
    return 'complex'


def _unquote(value_text):
    """Return the inner text of a quoted string value (no surrounding quotes)."""
    v = value_text.strip()
    if len(v) >= 2 and v[0] in '"\'' and v[-1] == v[0]:
        return v[1:-1]
    return v


def _quote_char(value_text):
    """Quote character the value currently uses (default double quote)."""
    v = value_text.strip()
    if len(v) >= 2 and v[0] in '"\'' and v[-1] == v[0]:
        return v[0]
    return '"'


def _quote(text, preferred='"'):
    """Wrap text in quotes, preferring `preferred` but keeping the result valid.

    If the chosen quote appears in the text, switch to the other quote; if both
    appear, escape the preferred one with a backslash.
    """
    if preferred not in text:
        return preferred + text + preferred
    other = "'" if preferred == '"' else '"'
    if other not in text:
        return other + text + other
    escaped = text.replace('\\', '\\\\').replace(preferred, '\\' + preferred)
    return preferred + escaped + preferred


def parse_schema(example_path):
    """Parse config.py.example into an ordered list of Setting objects.

    A comment block immediately preceding an assignment (no blank line between)
    becomes that setting's help text. A comment block followed by a blank line is
    treated as a section header carried onto the following settings.
    """
    with open(example_path, 'r') as f:
        lines = f.read().splitlines()

    settings = []
    seen = set()
    comment_buf = []          # accumulated comment lines (without leading '# ')
    current_section = ''
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('#'):
            # Is this a commented-out example assignment (e.g. used_space_paths)?
            m = COMMENTED_ASSIGN_RE.match(line)
            if m and m.group('key') not in seen and m.group('key') not in HIDDEN_KEYS:
                key = m.group('key')
                seen.add(key)
                settings.append(Setting(key, '', 'complex',
                                        '\n'.join(comment_buf), current_section, ''))
                comment_buf = []
                i += 1
                continue
            # Plain comment: accumulate, stripping the leading '# ' / '#'.
            text = stripped[1:]
            comment_buf.append(text[1:] if text.startswith(' ') else text)
            i += 1
            continue

        if stripped == '':
            # A comment block followed by a blank line is a section header.
            if comment_buf:
                current_section = comment_buf[-1].strip()
            comment_buf = []
            i += 1
            continue

        m = ASSIGN_RE.match(line)
        if m and m.group('key') not in seen and m.group('key') not in HIDDEN_KEYS:
            key = m.group('key')
            value_text = m.group('value').strip()
            seen.add(key)
            settings.append(Setting(key, value_text, _infer_type(value_text),
                                    '\n'.join(comment_buf), current_section,
                                    value_text))
        comment_buf = []
        i += 1

    return settings


def parse_current_values(config_path):
    """Return {key: value_text} for top-level assignments in config.py."""
    values = {}
    if not os.path.exists(config_path):
        return values
    with open(config_path, 'r') as f:
        for line in f.read().splitlines():
            if line.strip().startswith('#'):
                continue
            m = ASSIGN_RE.match(line)
            if m:
                values.setdefault(m.group('key'), m.group('value').strip())
    return values


def write_back(config_path, changes):
    """Apply {key: new_value_text} to config.py, preserving everything else.

    Only the value portion of each changed assignment is replaced; indentation
    and trailing inline comments are kept. Keys not present in the file are
    appended at the end. Written atomically.
    """
    if not changes:
        return
    with open(config_path, 'r') as f:
        lines = f.read().splitlines(keepends=True)

    remaining = dict(changes)
    for idx, line in enumerate(lines):
        if line.strip().startswith('#'):
            continue
        m = ASSIGN_RE.match(line.rstrip('\n'))
        if not m:
            continue
        key = m.group('key')
        if key in remaining:
            newline = '\n' if line.endswith('\n') else ''
            comment = m.group('comment') or ''
            lines[idx] = m.group('prefix') + remaining.pop(key) + comment + newline

    appended = []
    for key, value in remaining.items():
        appended.append("{} = {}\n".format(key, value))
    if appended:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] = lines[-1] + '\n'
        lines.extend(appended)

    tmp = config_path + '.tmp'
    with open(tmp, 'w') as f:
        f.writelines(lines)
    os.replace(tmp, config_path)


class ConfiguratorUI:
    def __init__(self, stdscr, settings, config_path):
        self.stdscr = stdscr
        self.settings = settings
        self.config_path = config_path
        self.selected = 0
        self.top = 0          # first visible row in the list viewport
        self.dirty = False
        self.saved_any = False  # True once any save succeeds this session
        self.status = ''

    # ---- value helpers -------------------------------------------------
    def _current_changes(self):
        """Settings whose value the user actually changed this session."""
        return {s.key: s.value_text for s in self.settings
                if s.type != 'complex' and s.value_text != s.original_text}

    # ---- rendering -----------------------------------------------------
    def _put(self, y, x, text, attr=curses.A_NORMAL):
        """addnstr that never raises on the bottom-right corner or overflow."""
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        # Writing into the last cell of the screen advances the cursor off the
        # window and errors, so leave the final column untouched.
        avail = w - x - 1
        if avail <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, text, avail, attr)
        except curses.error:
            pass

    def draw(self):
        scr = self.stdscr
        scr.erase()
        h, w = scr.getmaxyx()
        cur = self.settings[self.selected]

        # Bottom-anchored layout (rows counted up from the last line):
        #   h-1 footer | h-2 status | h-3 default | h-7..h-4 help | h-8 separator
        help_rows = 4
        footer_row = h - 1
        status_row = h - 2
        default_row = h - 3
        help_top = default_row - help_rows          # first help row
        sep_row = help_top - 1
        list_h = max(1, sep_row - 1)                 # list occupies rows 1..sep_row-1

        # Keep selection within the viewport.
        if self.selected < self.top:
            self.top = self.selected
        elif self.selected >= self.top + list_h:
            self.top = self.selected - list_h + 1

        title = " rpi-mqtt-monitor config "
        self._put(0, 0, title.ljust(w), curses.A_REVERSE | curses.A_BOLD)

        row = 1
        for idx in range(self.top, min(len(self.settings), self.top + list_h)):
            s = self.settings[idx]
            is_sel = (idx == self.selected)
            label = s.key.ljust(22)
            value = s.value_text if s.type != 'complex' else '(complex)'
            text = "  {} = {}".format(label, value)
            attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
            marker = '>' if is_sel else ' '
            self._put(row, 0, (marker + text).ljust(w), attr)
            row += 1

        # Detail pane.
        self._put(sep_row, 0, "-" * w)
        help_lines = (cur.help or "(no description)").split('\n')
        for i in range(help_rows):
            line = help_lines[i] if i < len(help_lines) else ""
            self._put(help_top + i, 0, " " + line)
        default_disp = cur.default_text if cur.type != 'complex' else 'edit in config.py'
        section_disp = "  [{}]".format(cur.section) if cur.section else ""
        self._put(default_row, 0,
                  " default: {}{}".format(default_disp, section_disp), curses.A_DIM)

        if self.status:
            self._put(status_row, 0, (" " + self.status).ljust(w), curses.A_BOLD)

        # Footer.
        dirty_mark = " *unsaved*" if self.dirty else ""
        if cur.type == 'complex':
            hint = "up/down move  s save  q quit  (complex: edit in config.py)"
        else:
            hint = "up/down move  enter edit  s save  q quit"
        footer = " {}{}".format(hint, dirty_mark)
        self._put(footer_row, 0, footer.ljust(w), curses.A_REVERSE)
        scr.refresh()

    # ---- editing -------------------------------------------------------
    def _prompt(self, prompt_text):
        """Read a line of text from the bottom of the screen.

        Returns the entered string (empty string if the user just pressed Enter),
        or None if input was aborted.
        """
        scr = self.stdscr
        h, w = scr.getmaxyx()
        label = " " + prompt_text + " "
        self._put(h - 1, 0, label.ljust(w), curses.A_REVERSE)
        col = min(len(label), w - 2)
        curses.echo()
        curses.curs_set(1)
        try:
            raw = scr.getstr(h - 1, col, max(1, w - col - 1))
            value = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        except Exception:
            value = None
        curses.noecho()
        curses.curs_set(0)
        return value

    def _edit_line(self, prompt_text, initial=''):
        """Edit a value on the bottom line, pre-filled with `initial`.

        Supports typing printable characters and Backspace. Enter accepts the
        current buffer (which may be empty); Esc cancels and returns None.
        """
        scr = self.stdscr
        curses.curs_set(1)
        buf = list(initial)
        try:
            while True:
                h, w = scr.getmaxyx()
                label = " " + prompt_text + " "
                self._put(h - 1, 0, (label + ''.join(buf)).ljust(w),
                          curses.A_REVERSE)
                try:
                    scr.move(h - 1, min(len(label) + len(buf), w - 1))
                except curses.error:
                    pass
                scr.refresh()
                ch = scr.getch()
                if ch in (curses.KEY_ENTER, 10, 13):
                    return ''.join(buf)
                if ch == 27:                       # Esc cancels
                    return None
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    if buf:
                        buf.pop()
                elif 32 <= ch <= 126:              # printable ASCII
                    buf.append(chr(ch))
                # other keys (arrows, function keys, etc.) are ignored
        finally:
            curses.curs_set(0)

    def edit_selected(self):
        s = self.settings[self.selected]
        self.status = ''
        if s.key == 'cpu_thermal_zone':
            self._pick_thermal_zone(s)
            return
        if s.type == 'bool':
            s.value_text = 'False' if s.value_text == 'True' else 'True'
            self.dirty = True
        elif s.type == 'int':
            raw = self._edit_line("{} (integer, Esc=cancel):".format(s.key),
                                  initial=s.value_text)
            if raw is None:
                return
            raw = raw.strip()
            if raw == '':
                return
            if re.fullmatch(r'-?\d+', raw):
                if raw != s.value_text:
                    s.value_text = raw
                    self.dirty = True
            else:
                self.status = "Not a valid integer: {!r}".format(raw)
        elif s.type == 'str':
            raw = self._edit_line("{} (text, Esc=cancel):".format(s.key),
                                  initial=_unquote(s.value_text))
            if raw is None:                        # cancelled; empty is allowed
                return
            new_value = _quote(raw, _quote_char(s.value_text))
            if new_value != s.value_text:
                s.value_text = new_value
                self.dirty = True
        else:
            self.status = "Complex value - edit it directly in config.py"

    def _select_from_list(self, title, items):
        """Modal pick-list. Returns the chosen index, or None if cancelled.

        up/down or j/k move, Enter chooses, Esc cancels. Renders over the screen
        using the same helpers/styling as the main view.
        """
        if not items:
            return None
        scr = self.stdscr
        sel = 0
        while True:
            scr.erase()
            h, w = scr.getmaxyx()
            self._put(0, 0, (" " + title).ljust(w), curses.A_REVERSE | curses.A_BOLD)
            list_h = max(1, h - 2)
            top = 0
            if sel >= list_h:
                top = sel - list_h + 1
            row = 1
            for idx in range(top, min(len(items), top + list_h)):
                is_sel = (idx == sel)
                marker = '>' if is_sel else ' '
                attr = curses.A_REVERSE if is_sel else curses.A_NORMAL
                self._put(row, 0, "{} {}".format(marker, items[idx]).ljust(w), attr)
                row += 1
            self._put(h - 1, 0,
                      " up/down move  enter select  Esc cancel".ljust(w),
                      curses.A_REVERSE)
            scr.refresh()
            ch = scr.getch()
            if ch in (curses.KEY_UP, ord('k')):
                sel = max(0, sel - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                sel = min(len(items) - 1, sel + 1)
            elif ch in (curses.KEY_ENTER, 10, 13):
                return sel
            elif ch == 27:                     # Esc cancels
                return None

    def _pick_thermal_zone(self, s):
        """Let the user pick cpu_thermal_zone from the sensors psutil reports.

        Falls back to free-text entry if psutil is unavailable or reports no
        temperature sensors, so the field stays usable everywhere.
        """
        custom_label = "Custom value…"
        keys = []
        try:
            import psutil
            temps = psutil.sensors_temperatures()
            for key in sorted(temps):
                readings = temps[key]
                if readings and readings[0].current is not None:
                    keys.append("{}  ({:.1f}°C)".format(key, readings[0].current))
                else:
                    keys.append(key)
            zone_keys = sorted(temps)
        except Exception:
            keys = []
            zone_keys = []

        if not keys:
            self.status = "No sensors detected via psutil - enter the key manually"
            raw = self._edit_line("{} (text, Esc=cancel):".format(s.key),
                                  initial=_unquote(s.value_text))
            if raw is None:
                return
            new_value = _quote(raw, _quote_char(s.value_text))
            if new_value != s.value_text:
                s.value_text = new_value
                self.dirty = True
            return

        choice = self._select_from_list(
            "Select CPU temperature sensor (cpu_thermal_zone)",
            keys + [custom_label])
        if choice is None:
            return
        if choice == len(keys):                # Custom value...
            raw = self._edit_line("{} (text, Esc=cancel):".format(s.key),
                                  initial=_unquote(s.value_text))
            if raw is None:
                return
            new_value = _quote(raw, _quote_char(s.value_text))
        else:
            new_value = _quote(zone_keys[choice], _quote_char(s.value_text))
        if new_value != s.value_text:
            s.value_text = new_value
            self.dirty = True

    def save(self):
        try:
            write_back(self.config_path, self._current_changes())
            for s in self.settings:
                s.original_text = s.value_text
            self.dirty = False
            self.saved_any = True
            self.status = "Saved to {}".format(self.config_path)
        except PermissionError:
            self.status = "Permission denied writing {} (try sudo)".format(
                self.config_path)
        except Exception as e:
            self.status = "Error saving: {}".format(e)

    def confirm_quit(self):
        if not self.dirty:
            return True
        ans = self._prompt("Unsaved changes. Save before quitting? (y/n/c):")
        if ans is None:
            return False
        ans = ans.strip().lower()
        if ans.startswith('y'):
            self.save()
            return not self.dirty
        if ans.startswith('n'):
            return True
        return False  # cancel

    # ---- key dispatch --------------------------------------------------
    def handle_key(self, ch):
        """Process one keypress. Returns False when the app should quit."""
        last = len(self.settings) - 1
        if ch in (curses.KEY_UP, ord('k')):
            self.selected = max(0, self.selected - 1)
            self.status = ''
        elif ch in (curses.KEY_DOWN, ord('j')):
            self.selected = min(last, self.selected + 1)
            self.status = ''
        elif ch == curses.KEY_NPAGE:
            self.selected = min(last, self.selected + 10)
        elif ch == curses.KEY_PPAGE:
            self.selected = max(0, self.selected - 10)
        elif ch == curses.KEY_HOME:
            self.selected = 0
        elif ch == curses.KEY_END:
            self.selected = last
        elif ch in (curses.KEY_ENTER, 10, 13, ord(' ')):
            self.edit_selected()
        elif ch in (ord('s'), ord('S')):
            self.save()
        elif ch in (ord('q'), ord('Q')):
            return self.confirm_quit() is False
        return True

    # ---- main loop -----------------------------------------------------
    def loop(self):
        curses.curs_set(0)
        while True:
            self.draw()
            ch = self.stdscr.getch()
            if not self.handle_key(ch):
                break


def run(config_path, example_path):
    """Entry point invoked from `rpi-mqtt-monitor --config`."""
    if not os.path.exists(example_path):
        print("Cannot find config schema: {}".format(example_path))
        return
    if not os.path.exists(config_path):
        print("No config.py found at {}.\nRun the installer first, or copy "
              "config.py.example to config.py.".format(config_path))
        return

    settings = parse_schema(example_path)
    current = parse_current_values(config_path)
    for s in settings:
        if s.key in current and s.type != 'complex':
            s.value_text = current[s.key]
            s.original_text = s.value_text

    ui_holder = {}

    def _run(stdscr):
        ui = ConfiguratorUI(stdscr, settings, config_path)
        ui_holder['ui'] = ui
        ui.loop()

    curses.wrapper(_run)

    ui = ui_holder.get('ui')
    if ui is not None and ui.saved_any:
        print("Settings saved. If running as a service, restart it for changes "
              "to take effect:")
        print("    sudo systemctl restart rpi-mqtt-monitor.service")


if __name__ == '__main__':
    here = os.path.dirname(os.path.realpath(__file__))
    run(os.path.join(here, 'config.py'), os.path.join(here, 'config.py.example'))
