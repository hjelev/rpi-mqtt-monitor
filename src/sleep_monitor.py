"""Watch for system suspend/resume via systemd-logind over D-Bus.

logind broadcasts PrepareForSleep(true) just before suspend/hibernate and
PrepareForSleep(false) after resume. To make sure we get to act before the
machine actually sleeps, we hold a logind "delay" inhibitor lock: logind waits
until we release it (or until InhibitDelayMaxSec passes, so a hung handler can
never block suspend for long).

Uses jeepney (pure Python, no compiled parts). It is imported lazily so systems
without it, or without a system bus / logind, simply report the feature as
unavailable.
"""

import time

LOGIN1_NAME = 'org.freedesktop.login1'
LOGIN1_PATH = '/org/freedesktop/login1'
LOGIN1_IFACE = 'org.freedesktop.login1.Manager'

# How often the blocking D-Bus read wakes up to check for shutdown.
POLL_SECONDS = 1.0
# Wait before reconnecting if the D-Bus connection drops.
RETRY_SECONDS = 30


def build_match_rules():
    """Return (bus_rule, local_rule) for logind's PrepareForSleep signal.

    bus_rule is registered with AddMatch: the bus daemon resolves the well-known
    sender name, so only the real logind can trigger us. local_rule is jeepney's
    in-process filter, which compares the sender header literally; signals carry
    logind's unique name (e.g. ':1.2'), so it must not include the sender.
    """
    from jeepney import MatchRule
    fields = dict(type='signal', path=LOGIN1_PATH, interface=LOGIN1_IFACE,
                  member='PrepareForSleep')
    return MatchRule(sender=LOGIN1_NAME, **fields), MatchRule(**fields)


class SleepMonitor:
    def __init__(self, on_sleep, on_wake, stop_event, app_name='rpi-mqtt-monitor'):
        """on_sleep() runs before suspend while we still hold the inhibitor lock;
        on_wake() runs after resume. Both are called from this monitor's thread."""
        self.on_sleep = on_sleep
        self.on_wake = on_wake
        self.stop_event = stop_event
        self.app_name = app_name
        self._lock_fd = None

    def run(self):
        """Thread entry point. Returns if jeepney or logind is unavailable."""
        try:
            from jeepney import DBusAddress, message_bus, new_method_call
            from jeepney.io.blocking import open_dbus_connection, Proxy
        except ImportError:
            print("Sleep state: jeepney is not installed (pip install jeepney); feature disabled.")
            return

        self._jeepney = (DBusAddress, new_method_call)
        bus_rule, local_rule = build_match_rules()

        while not self.stop_event.is_set():
            conn = None
            try:
                conn = open_dbus_connection(bus='SYSTEM', enable_fds=True)
                Proxy(message_bus, conn).AddMatch(bus_rule)
                with conn.filter(local_rule, bufsize=8) as queue:
                    self._take_lock(conn)
                    print("Sleep state: watching for suspend/resume via logind.")
                    self._loop(conn, queue)
            except Exception as e:
                print("Sleep state: D-Bus error: {}".format(e))
                if conn is None:
                    # Could not even reach the system bus (no systemd/logind?).
                    print("Sleep state: system bus unavailable; feature disabled.")
                    return
            finally:
                self._release_lock()
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self.stop_event.wait(RETRY_SECONDS)

    def _loop(self, conn, queue):
        while not self.stop_event.is_set():
            try:
                msg = conn.recv_until_filtered(queue, timeout=POLL_SECONDS)
            except TimeoutError:
                continue
            going_to_sleep = bool(msg.body[0])
            if going_to_sleep:
                self._safe_call(self.on_sleep, "sleep")
                # Let the suspend proceed.
                self._release_lock()
            else:
                # Re-arm for the next suspend first, so a slow on_wake can't
                # make us miss it.
                self._take_lock(conn)
                self._safe_call(self.on_wake, "wake")

    def _take_lock(self, conn):
        if self._lock_fd is not None:
            return
        from jeepney.wrappers import unwrap_msg
        DBusAddress, new_method_call = self._jeepney
        login1 = DBusAddress(LOGIN1_PATH, bus_name=LOGIN1_NAME, interface=LOGIN1_IFACE)
        msg = new_method_call(login1, 'Inhibit', 'ssss',
                              ('sleep', self.app_name,
                               'Publish sleep state to MQTT', 'delay'))
        try:
            self._lock_fd = unwrap_msg(conn.send_and_get_reply(msg, timeout=5))[0]
        except Exception as e:
            # Still useful without the lock: we get the signal, just with no
            # guarantee of finishing before the machine sleeps.
            print("Sleep state: could not take inhibitor lock: {}".format(e))

    def _release_lock(self):
        if self._lock_fd is not None:
            try:
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None

    @staticmethod
    def _safe_call(func, label):
        start = time.monotonic()
        try:
            func()
        except Exception as e:
            print("Sleep state: {} handler failed: {}".format(label, e))
        print("Sleep state: {} handled in {:.2f}s".format(label, time.monotonic() - start))
