"""updates translation files for a language from the Weblate project and commits them"""

from argparse import ArgumentParser
from dataclasses import dataclass
from logging import basicConfig, error, info, warning
from os import getenv
from pathlib import Path
from re import match
from shutil import rmtree
from subprocess import call, run

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from wlc import Project, Weblate, WeblateThrottlingError


def _update_translation(language: str, version: str, weblate_key: str) -> None:
    _call('git diff --exit-code')
    _clear_files()
    _download_translations(language, Version(version), weblate_key)
    changed = _get_changed_files()
    added = _get_new_files()
    if all_ := changed + added:
        _call(f'git add {" ".join(all_)}')
        _call('git commit -m "Update translation from Weblate"')
    _call('git restore .')  # discard ignored files


def _clear_files():
    for path in Path().iterdir():
        if path.name.startswith('.'):
            continue
        if path.is_dir() and not path.is_symlink():
            rmtree(path)
        if path.suffix == '.po':
            path.unlink()


def _download_translations(language: str, version: "Version", weblate_key: str) -> None:
    weblate = Weblate(weblate_key, 'https://hosted.weblate.org/api/')
    project = Project(weblate, 'https://hosted.weblate.org/api/projects/python-docs/')
    _validate_language(language, project)
    with logging_redirect_tqdm():
        for selected_category in project.categories():
            if selected_category.name == version.weblate_category_name():
                break

        for component in tqdm(project.list()):
            if component.category and component.category.name != selected_category.name:
                continue
            if component.is_glossary:
                continue
            translations = component.list()
            while (translation := next(translations, None)) and translation.language.code != 'pl':
                pass
            if not translation:
                info(f"{component.slug} doesn't have a {language} translation")
                continue
            try:
                content = translation.download()
            except WeblateThrottlingError:
                error(f'Throttled on {component.slug}', exc_info=True)
                break
            path = Path(component.filemask.removeprefix(f'*/{version.directory_name()}/'))
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)


@dataclass
class Version:
    number: str

    def is_latest(self):
        return self.number == "3.12"

    def weblate_category_name(self):
        return self.number

    def directory_name(self):
        return self.is_latest() and "latest" or self.number


def _validate_language(language: str, project: Project) -> None:
    for l in project.languages():
        if l.code == language:
            break
    else:
        raise SystemError(f'{language} is an incorrect language')


def _get_changed_files() -> list[str]:
    diff = _run("git diff -I'^\"POT-Creation-Date: ' --numstat")
    return [match(r'\d+\t\d+\t(.*)', line).group(1) for line in diff.splitlines()]


def _get_new_files() -> list[str]:
    ls_files = _run('git ls-files -o -d --exclude-standard')
    return ls_files.splitlines()


def _call(command: str):
    if (return_code := call(command, shell=True)) != 0:
        exit(return_code)


def _run(command: str) -> str:
    if (process := run(command, shell=True, capture_output=True)).returncode != 0:
        exit(process.returncode)
    return process.stdout.decode()


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('language')
    parser.add_argument('version')
    options = parser.parse_args()

    basicConfig(level='INFO')

    if not (weblate_key := getenv('KEY')):
        warning('Not authenticated, you will be heavy throttled')

    _update_translation(options.language, options.version, weblate_key=weblate_key)
