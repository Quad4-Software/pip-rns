"""Detect project name and dependencies from common Python project layouts."""

import os
import re

REQUIREMENTS_CANDIDATES = (
    "requirements.txt",
    "requirements/prod.txt",
    "requirements/base.txt",
    "requirements/main.txt",
)

OPTIONAL_REQUIREMENTS = (
    "requirements-dev.txt",
    "requirements/dev.txt",
    "requirements/test.txt",
)

PYPROJECT = "pyproject.toml"
SETUP_CFG = "setup.cfg"
SETUP_PY = "setup.py"


class ProjectError(Exception):
    pass


class ProjectInfo:
    """Detected metadata from a Python project directory."""

    def __init__(self, name=None, requirements=None, source=None, project_dir=None):
        self.name = name
        self.requirements = list(requirements or [])
        self.source = source
        self.project_dir = project_dir or "."


def detect_project(project_dir="."):
    """
    Detect project name and dependencies from pyproject.toml or requirements files.

    Checks pyproject.toml first, then requirements.txt and common variants.
    """
    project_dir = os.path.abspath(project_dir)
    if not os.path.isdir(project_dir):
        raise ProjectError(f"Not a directory: {project_dir}")

    pyproject_path = os.path.join(project_dir, PYPROJECT)
    if os.path.isfile(pyproject_path):
        info = _from_pyproject(pyproject_path, project_dir)
        if info.requirements or info.name:
            return info

    for rel in REQUIREMENTS_CANDIDATES:
        path = os.path.join(project_dir, rel)
        if os.path.isfile(path):
            reqs = _read_requirements(path)
            name = _name_from_dir(project_dir)
            return ProjectInfo(
                name=name,
                requirements=reqs,
                source=rel,
                project_dir=project_dir,
            )

    setup_cfg = os.path.join(project_dir, SETUP_CFG)
    if os.path.isfile(setup_cfg):
        info = _from_setup_cfg(setup_cfg, project_dir)
        if info.requirements or info.name:
            return info

    setup_py = os.path.join(project_dir, SETUP_PY)
    if os.path.isfile(setup_py):
        info = _from_setup_py(setup_py, project_dir)
        if info.requirements or info.name:
            return info

    raise ProjectError(
        f"No pyproject.toml, setup.py, or requirements file found in {project_dir}"
    )


def merge_optional_requirements(info, project_dir, include_dev=False):
    """Append optional dev/test requirements when requested."""
    if not include_dev:
        return info.requirements
    reqs = list(info.requirements)
    for rel in OPTIONAL_REQUIREMENTS:
        path = os.path.join(project_dir, rel)
        if os.path.isfile(path):
            for line in _read_requirements(path):
                if line not in reqs:
                    reqs.append(line)
    return reqs


def _name_from_dir(project_dir):
    return os.path.basename(os.path.normpath(project_dir))


def _read_requirements(path):
    reqs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-r ") or line.startswith("--"):
                continue
            reqs.append(line)
    return reqs


def _from_pyproject(path, project_dir):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    data = _parse_toml_subset(text)
    name = None
    requirements = []

    project = data.get("project", {})
    if isinstance(project, dict):
        name = project.get("name")
        requirements.extend(_normalize_dep_list(project.get("dependencies")))

    poetry = data.get("tool", {}).get("poetry", {})
    if isinstance(poetry, dict):
        if not name:
            name = poetry.get("name")
        poetry_deps = poetry.get("dependencies", {})
        if isinstance(poetry_deps, dict):
            requirements.extend(_poetry_dependencies(poetry_deps))
        else:
            requirements.extend(_normalize_dep_list(poetry_deps))

    poetry_groups = poetry.get("group", {}) if isinstance(poetry, dict) else {}
    if isinstance(poetry_groups, dict):
        for group in poetry_groups.values():
            if isinstance(group, dict):
                requirements.extend(_normalize_dep_list(group.get("dependencies")))

    optional = (
        project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    )
    if isinstance(optional, dict):
        for deps in optional.values():
            requirements.extend(_normalize_dep_list(deps))

    requirements = _dedupe_requirements(requirements)

    return ProjectInfo(
        name=_normalize_name(name) if name else _name_from_dir(project_dir),
        requirements=requirements,
        source=PYPROJECT,
        project_dir=project_dir,
    )


def _from_setup_cfg(path, project_dir):
    name = None
    requirements = []
    section = None
    in_requires = False

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                in_requires = False
                continue
            if section == "metadata" and line.lower().startswith("name"):
                name = line.split("=", 1)[1].strip()
            if section == "options":
                if line.lower().startswith("install_requires"):
                    rest = line.split("=", 1)[1].strip()
                    if rest:
                        requirements.append(rest)
                    in_requires = True
                    continue
                if in_requires and raw.startswith((" ", "\t")):
                    requirements.append(line)

    return ProjectInfo(
        name=_normalize_name(name) if name else _name_from_dir(project_dir),
        requirements=_dedupe_requirements(requirements),
        source=SETUP_CFG,
        project_dir=project_dir,
    )


def _from_setup_py(path, project_dir):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    name = None
    name_match = re.search(r"""name\s*=\s*['"]([^'"]+)['"]""", text)
    if name_match:
        name = name_match.group(1)

    requirements = []
    requires_match = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if requires_match:
        block = requires_match.group(1)
        for item in re.findall(r"""['"]([^'"]+)['"]""", block):
            requirements.append(item)

    return ProjectInfo(
        name=_normalize_name(name) if name else _name_from_dir(project_dir),
        requirements=_dedupe_requirements(requirements),
        source=SETUP_PY,
        project_dir=project_dir,
    )


def _parse_toml_subset(text):
    """
    Minimal TOML parser for pyproject fields used by opip.

    Supports sections, key = value, inline arrays, and multiline arrays.
    """
    root = {}
    section_keys = []

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].split("#", 1)[0].strip()
        i += 1
        if not line:
            continue

        if line.startswith("[["):
            continue

        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            section_keys = section_name.split(".")
            node = root
            for key in section_keys:
                nxt = node.get(key)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[key] = nxt
                node = nxt
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith("["):
            if value.endswith("]") and value != "[]":
                parsed = _split_toml_array(value[1:-1])
            elif value == "[]":
                parsed = []
            else:
                remainder = value[1:].strip().rstrip(",")
                parsed = _split_toml_array(remainder) if remainder else []
                extra, i = _read_multiline_array_continuation(lines, i)
                parsed.extend(extra)
            _assign(root, section_keys, key, parsed)
            continue

        parsed = _parse_toml_value(value)
        _assign(root, section_keys, key, parsed)

    return root


def _read_multiline_array_continuation(lines, start_index):
    items = []
    i = start_index
    while i < len(lines):
        line = lines[i].split("#", 1)[0].strip()
        i += 1
        if not line:
            continue
        closing = line.endswith("]")
        if closing:
            line = line[:-1].strip()
        if line.endswith(","):
            line = line[:-1]
        if line:
            items.extend(_split_toml_array(line))
        if closing:
            break
    return items, i


def _split_toml_array(text):
    if not text.strip():
        return []
    parts = []
    current = []
    in_str = False
    quote = None
    for ch in text:
        if in_str:
            current.append(ch)
            if ch == quote:
                in_str = False
            continue
        if ch in ("'", '"'):
            in_str = True
            quote = ch
            current.append(ch)
            continue
        if ch == ",":
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [_parse_toml_value(p) for p in parts if p.strip()]


def _parse_toml_value(value):
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return _split_toml_array(inner)
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def _assign(root, section_keys, key, value):
    node = root
    for part in section_keys:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[key] = value


def _normalize_dep_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _poetry_dependencies(deps):
    result = []
    for name, spec in deps.items():
        if name.lower() == "python":
            continue
        if isinstance(spec, dict):
            version = spec.get("version", "*")
            result.append(f"{name}{_poetry_spec(version)}")
        elif spec is None:
            result.append(name)
        else:
            result.append(f"{name}{_poetry_spec(str(spec))}")
    return result


def _poetry_spec(spec):
    spec = spec.strip()
    if not spec or spec == "*":
        return ""
    if spec.startswith(("^", "~", ">=", "<=", "==", "!=", ">")):
        if spec.startswith("^"):
            return f">={spec[1:]}"
        if spec.startswith("~"):
            return f">={spec[1:]}"
        return spec
    return f"=={spec}"


def _normalize_name(name):
    if not name:
        return name
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-").lower()


def _dedupe_requirements(requirements):
    seen = set()
    out = []
    for req in requirements:
        key = req.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(req.strip())
    return out
