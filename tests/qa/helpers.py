"""Shared helpers for QA tests."""
import os


def print_section(title):
    print(f'\n{"=" * 70}')
    print(f'  {title}')
    print(f'{"=" * 70}')


def print_tree(directory, indent=0, prefix=''):
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        label = f'{prefix}{entry}'
        if os.path.isdir(full):
            print(f'{"  " * indent}{label}/')
            print_tree(full, indent + 1, '')
        else:
            size = os.path.getsize(full)
            print(f'{"  " * indent}{label}  ({size} bytes)')


def count_bare_files(vault_dir):
    """Count files in each bare/ subdirectory."""
    bare_dir = os.path.join(vault_dir, '.sg_vault', 'bare')
    counts = {}
    total  = 0
    for subdir in sorted(os.listdir(bare_dir)):
        subdir_path = os.path.join(bare_dir, subdir)
        if os.path.isdir(subdir_path):
            count = len([f for f in os.listdir(subdir_path)
                         if os.path.isfile(os.path.join(subdir_path, f))])
            counts[subdir] = count
            total += count
    counts['total'] = total
    return counts


def count_working_files(vault_dir):
    """Count plaintext working files (excluding .sg_vault/)."""
    count = 0
    for root, dirs, files in os.walk(vault_dir):
        dirs[:] = [d for d in dirs if d != '.sg_vault']
        count += len(files)
    return count
