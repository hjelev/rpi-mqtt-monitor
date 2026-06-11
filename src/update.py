import ast
import os
import subprocess
import config
import sys


def safe_literal_eval(node):
    try:
        return ast.literal_eval(node)
    except ValueError:
        return None


def get_assignments(filename):
    with open(filename) as f:
        tree = ast.parse(f.read(), filename)

    assignments = {
        node.targets[0].id: safe_literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    return assignments


def update_config(current_config, example_config):
    current_assignments = get_assignments(current_config)
    example_assignments = get_assignments(example_config)

    missing_assignments = {var: value for var, value in example_assignments.items() if var not in current_assignments}

    if missing_assignments:
        with open(current_config, 'ab+') as f:  # Open the file in binary mode
            f.seek(-1, os.SEEK_END)  # Move the cursor to the last character
            last_char = f.read(1)  # Read the last character

        # If the last character is not a newline, write a newline
        if last_char != b'\n':
            with open(current_config, 'a') as f:  # Open the file in text mode
                f.write('\n')

        # Write the missing assignments
        with open(current_config, 'a') as f:
            for var, value in missing_assignments.items():
                f.write('{} = {!r}\n'.format(var, value))


def display_config_differences(current_config, example_config, display=True):
    current_assignments = get_assignments(current_config)
    example_assignments = get_assignments(example_config)

    missing_assignments = {var: value for var, value in example_assignments.items() if var not in current_assignments}

    if missing_assignments:
        if display: 
            print("Missing variables:")
            for var, value in missing_assignments.items():
                print('\n{} = {!r}'.format(var, value))
        return True
    else:
        return False


def ensure_git_safe_directory(script_dir):
    """Mark the repo as a safe directory for the current user (idempotent).

    The service may run as root while the repo is owned by another user. Without
    this, modern git refuses describe/ls-remote/pull with a 'dubious ownership'
    error, which silently breaks the version check and the update button.
    """
    try:
        subprocess.run(['/usr/bin/git', 'config', '--global', '--add', 'safe.directory', script_dir],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        print("Warning: could not set git safe.directory: {}".format(e))


def check_git_version_remote(script_dir):
    ensure_git_safe_directory(script_dir)
    full_cmd = "/usr/bin/git -C {} ls-remote --tags origin | awk -F'/' '{{print $3}}' | sort -V | tail -n 1".format(script_dir)
    try:
        proc = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        result = out.decode("utf-8")
        if proc.returncode != 0:
            print("Error checking remote version: {}".format(err.decode("utf-8").strip()))
            return config.version
    except Exception as e:
        print("Error: {}".format(e))
        return config.version

    latest_tag = result.strip()
    # On any failure fall back to the installed version so HA never shows a
    # phantom "update available" pointing at a bogus version.
    return latest_tag if latest_tag else config.version


def update_config_version(version, script_dir):
    with open(script_dir + '/config.py', 'r') as f:
        lines = f.readlines()

    with open(script_dir + '/config.py', 'w') as f:
        print(":: Updating config version to {}".format(version))
        for line in lines:
            if 'version = ' in line:
                f.write('version = "{}"\n'.format(version))
            else:
                f.write(line)


def install_requirements(script_dir):
    main_dir_path = os.path.dirname(script_dir)
    requirements_path = os.path.join(main_dir_path, 'requirements.txt')
    activate_script = os.path.join(main_dir_path, 'rpi_mon_env' ,'bin', 'activate')
    command = f"source {activate_script} && pip install -q -r {requirements_path}"

    try:
        subprocess.run(command, shell=True, check=True, executable='/bin/bash')
        print("Requirements installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while installing requirements: {e}")
        sys.exit(1)


def do_update(script_dir, version=config.version, git_update=True, config_update=True,
              progress_cb=None):
    def report(pct):
        if progress_cb:
            try:
                progress_cb(pct)
            except Exception:
                pass

    print("Current version: {}".format(config.version))
    report(0)
    if git_update:
        print(":: Updating git repository", script_dir)
        ensure_git_safe_directory(script_dir)
        try:
            result = subprocess.run(['/usr/bin/git', '-C', script_dir, 'pull'],
                                    check=True, universal_newlines=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            # Surface the failure (visible in journalctl) instead of letting the
            # exception kill the caller thread silently, and abort the update.
            print(":: git pull failed: {}".format((e.stderr or e.stdout or str(e)).strip()))
            return False
        report(30)
        install_requirements(script_dir)
        report(70)

    if display_config_differences(script_dir + '/config.py', script_dir + '/config.py.example') and config_update:
        print(":: Updating config.py")
        update_config(script_dir + '/config.py',script_dir + '/config.py.example')

    if version != config.version:
        update_config_version(version, script_dir)

    report(90)
    return True


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.realpath(__file__))
    do_update(script_dir,check_git_version_remote(script_dir))
    