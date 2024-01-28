import ast
import os
import subprocess


def get_assignments(filename):
    with open(filename) as f:
        tree = ast.parse(f.read(), filename)

    assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.walk(tree) if isinstance(node, ast.Assign)}
    return assignments

def update_config(current_config, example_config):
    current_assignments = get_assignments(current_config)
    example_assignments = get_assignments(example_config)

    missing_assignments = {var: value for var, value in example_assignments.items() if var not in current_assignments}

    if missing_assignments:
        with open(current_config, 'a') as f:
            for var, value in missing_assignments.items():
                f.write('\n{} = {!r}'.format(var, value))

def display_config_differences(current_config, example_config):
    current_assignments = get_assignments(current_config)
    example_assignments = get_assignments(example_config)

    missing_assignments = {var: value for var, value in example_assignments.items() if var not in current_assignments}

    if missing_assignments:
        print("Missing variables:")
        for var, value in missing_assignments.items():
            print('\n{} = {!r}'.format(var, value))
        return True
    else:
        return False


script_dir = os.path.dirname(os.path.realpath(__file__))
os.chdir(script_dir)

print(":: Updating git repository")
result = subprocess.run(['git', '-C', script_dir, 'pull'], check=True, text=True, capture_output=True)
print(result.stdout)

if display_config_differences('config.py', 'config.py.example'):
    print(":: Updating config.py")
    update_config('config.py', 'config.py.example')
else:
    print(":: No config.py updates needed")