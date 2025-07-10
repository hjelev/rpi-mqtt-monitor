import ast
import os
import subprocess
import config
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def safe_literal_eval(node):
    """Safely evaluate an AST node.

    Any :class:`ValueError` or :class:`SyntaxError` raised by
    :func:`ast.literal_eval` will result in ``None`` being returned
    instead of propagating the exception.
    """
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def get_assignments(filename):
    with open(filename) as f:
        tree = ast.parse(f.read(), filename)

    assignments = {node.targets[0].id: safe_literal_eval(node.value) for node in ast.walk(tree) if isinstance(node, ast.Assign)}
    return assignments


def update_config(current_config, example_config):
    current_assignments = get_assignments(current_config)
    example_assignments = get_assignments(example_config)

    missing_assignments = {var: value for var, value in example_assignments.items() if var not in current_assignments}

    if missing_assignments:
        with open(current_config, 'ab+') as f:  # Open the file in binary mode
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
            else:
                last_char = b''

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
            logger.info("Missing variables:")
            for var, value in missing_assignments.items():
                logger.info("%s = %r", var, value)
        return True
    else:
        return False


def check_git_version_remote(script_dir):
    """Return the newest tag from the remote repository."""
    try:
        subprocess.run(
            ["git", "-C", script_dir, "fetch", "--tags"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        result = subprocess.run(
            ["git", "-C", script_dir, "tag", "--sort=-v:refname"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        tags = result.stdout.strip().splitlines()
        latest_tag = tags[0] if tags else "0"
    except subprocess.CalledProcessError as e:
        logger.error("Error checking git version: %s", e)
        return config.version

    return latest_tag


def update_config_version(version, script_dir):
    with open(script_dir + '/config.py', 'r') as f:
        lines = f.readlines()

    with open(os.path.join(script_dir, 'config.py'), 'w') as f:
        logger.info("Updating config version to %s", version)
        for line in lines:
            if 'version = ' in line:
                f.write('version = "{}"\n'.format(version))
            else:
                f.write(line)


def install_requirements(script_dir):
    main_dir_path = os.path.dirname(script_dir)
    requirements_path = os.path.join(main_dir_path, 'requirements.txt')
    pip_executable = os.path.join(main_dir_path, 'rpi_mon_env', 'bin', 'pip')

    try:
        subprocess.run([pip_executable, 'install', '-q', '-r', requirements_path], check=True)
        logger.info("Requirements installed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error("An error occurred while installing requirements: %s", e)
        sys.exit(1)


def do_update(script_dir, version=config.version, git_update=True, config_update=True):
    logger.info("Current version: %s", config.version)
    if git_update:
        logger.info("Updating git repository %s", script_dir)
        result = subprocess.run(['git', '-C', script_dir, 'pull'], check=True, text=True, stdout=subprocess.PIPE)
        logger.info(result.stdout)
        install_requirements(script_dir)
        
    if display_config_differences(script_dir + '/config.py', script_dir + '/config.py.example') and config_update:
        logger.info("Updating config.py")
        update_config(script_dir + '/config.py',script_dir + '/config.py.example')

    if version != config.version:
        update_config_version(version, script_dir)


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.realpath(__file__))
    do_update(script_dir,check_git_version_remote(script_dir))
