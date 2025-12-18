"""Implements an importer that looks only in specific path (ignoring
sys.path), and uses a per-path cache in addition to sys.modules. This is
necessary because test modules in different directories frequently have the
same names, which means that the first loaded would mask the rest when using
the builtin importer.
"""
import logging
import os
import sys
from nose.config import Config

import importlib
import importlib.machinery
import importlib.util
import tokenize
from threading import RLock

# Thread lock for import operations
_import_lock = RLock()


def acquire_lock():
    """Acquire the import lock."""
    _import_lock.acquire()


def release_lock():
    """Release the import lock."""
    _import_lock.release()


# Module type constants
SEARCH_ERROR = 0
PY_SOURCE = 1
PY_COMPILED = 2
C_EXTENSION = 3
PY_RESOURCE = 4
PKG_DIRECTORY = 5
C_BUILTIN = 6
PY_FROZEN = 7
PY_CODERESOURCE = 8
IMP_HOOK = 9


def get_suffixes():
    extensions = [(s, 'rb', C_EXTENSION) for s in importlib.machinery.EXTENSION_SUFFIXES]
    source = [(s, 'r', PY_SOURCE) for s in importlib.machinery.SOURCE_SUFFIXES]
    bytecode = [(s, 'rb', PY_COMPILED) for s in importlib.machinery.BYTECODE_SUFFIXES]
    return extensions + source + bytecode


def load_package(name, path):
    if os.path.isdir(path):
        extensions = (importlib.machinery.SOURCE_SUFFIXES[:] +
                      importlib.machinery.BYTECODE_SUFFIXES[:])
        for extension in extensions:
            init_path = os.path.join(path, '__init__' + extension)
            if os.path.exists(init_path):
                path = init_path
                break
        else:
            raise ValueError(f'{path!r} is not a package')
    spec = importlib.util.spec_from_file_location(name, path,
                                                  submodule_search_locations=[])
    sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


def init_builtin(name):
    """Import a built-in module by name."""
    if name in sys.builtin_module_names:
        return importlib.import_module(name)
    return None


def is_builtin(name):
    """Check if a module is a built-in module."""
    return name in sys.builtin_module_names


def is_frozen(name):
    """Check if a module is a frozen module."""
    # In Python 3.11+, we can check the frozen modules
    try:
        spec = importlib.util.find_spec(name)
        if spec and spec.origin == 'frozen':
            return True
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    return False


def init_frozen(name):
    """Import a frozen module by name."""
    return importlib.import_module(name)


def find_module(name, path=None):
    """
    Search for a module.

    If path is omitted or None, search for a built-in, frozen or special
    module and continue search in sys.path. The module name cannot
    contain '.'; to search for a submodule of a package, pass the
    submodule name and the package's __path__.
    """
    if is_builtin(name):
        return None, None, ('', '', C_BUILTIN)
    elif is_frozen(name):
        return None, None, ('', '', PY_FROZEN)

    spec = importlib.machinery.PathFinder.find_spec(name, path)
    if spec is None:
        raise ImportError(f"No module named {name!r}", name=name)

    # RETURN (file, file_path, desc=(suffix, mode, type_))
    if spec.origin and os.path.splitext(os.path.basename(spec.origin))[0] == '__init__':
        return None, os.path.dirname(spec.origin), ('', '', PKG_DIRECTORY)

    if spec.origin is None:
        raise ImportError(f"No module named {name!r}", name=name)

    for suffix, mode, type_ in get_suffixes():
        if spec.origin.endswith(suffix):
            break
    else:
        suffix = '.py'
        mode = 'r'
        type_ = PY_SOURCE

    encoding = None
    if 'b' not in mode:
        with open(spec.origin, 'rb') as file:
            encoding = tokenize.detect_encoding(file.readline)[0]
    file = open(spec.origin, mode, encoding=encoding)
    return file, spec.origin, (suffix, mode, type_)


def load_module(name, file, filename, details):
    """
    Load a module, given information returned by find_module().

    The module name must include the full package name, if any.
    """
    suffix, mode, type_ = details
    if type_ == PKG_DIRECTORY:
        return load_package(name, filename)
    elif type_ == C_BUILTIN:
        return init_builtin(name)
    elif type_ == PY_FROZEN:
        return init_frozen(name)

    # PY_SOURCE
    spec = importlib.util.spec_from_file_location(name, filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

log = logging.getLogger(__name__)

try:
    _samefile = os.path.samefile
except AttributeError:
    def _samefile(src, dst):
        return (os.path.normcase(os.path.realpath(src)) ==
                os.path.normcase(os.path.realpath(dst)))


class Importer:
    """An importer class that does only path-specific imports. That
    is, the given module is not searched for on sys.path, but only at
    the path or in the directory specified.
    """
    def __init__(self, config=None):
        if config is None:
            config = Config()
        self.config = config

    def importFromPath(self, path, fqname):
        """Import a dotted-name package whose tail is at path. In other words,
        given foo.bar and path/to/foo/bar.py, import foo from path/to/foo then
        bar from path/to/foo/bar, returning bar.
        """
        # find the base dir of the package
        path_parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
        name_parts = fqname.split('.')
        if path_parts[-1] == '__init__.py':
            path_parts.pop()
        path_parts = path_parts[:-(len(name_parts))]
        dir_path = os.sep.join(path_parts)
        # then import fqname starting from that dir
        return self.importFromDir(dir_path, fqname)

    def importFromDir(self, dir, fqname):
        """Import a module *only* from path, ignoring sys.path and
        reloading if the version in sys.modules is not the one we want.
        """
        dir = os.path.normpath(os.path.abspath(dir))
        log.debug("Import %s from %s", fqname, dir)

        # FIXME reimplement local per-dir cache?

        # special case for __main__
        if fqname == '__main__':
            return sys.modules[fqname]

        if self.config.addPaths:
            add_path(dir, self.config)

        path = [dir]
        parts = fqname.split('.')
        part_fqname = ''
        mod = parent = fh = None

        for part in parts:
            if part_fqname == '':
                part_fqname = part
            else:
                part_fqname = "{}.{}".format(part_fqname, part)
            try:
                acquire_lock()
                log.debug("find module part %s (%s) in %s",
                          part, part_fqname, path)
                fh, filename, desc = find_module(part, path)
                old = sys.modules.get(part_fqname)
                if old is not None:
                    # test modules frequently have name overlap; make sure
                    # we get a fresh copy of anything we are trying to load
                    # from a new path
                    log.debug("sys.modules has %s as %s", part_fqname, old)
                    if (self.sameModule(old, filename)
                        or (self.config.firstPackageWins and
                            getattr(old, '__path__', None))):
                        mod = old
                    else:
                        del sys.modules[part_fqname]
                        mod = load_module(part_fqname, fh, filename, desc)
                else:
                    mod = load_module(part_fqname, fh, filename, desc)
            finally:
                if fh:
                    fh.close()
                release_lock()
            if parent:
                setattr(parent, part, mod)
            if hasattr(mod, '__path__'):
                path = mod.__path__
            parent = mod
        return mod

    def _dirname_if_file(self, filename):
        # We only take the dirname if we have a path to a non-dir,
        # because taking the dirname of a symlink to a directory does not
        # give the actual directory parent.
        if os.path.isdir(filename):
            return filename
        else:
            return os.path.dirname(filename)

    def sameModule(self, mod, filename):
        mod_paths = []
        if hasattr(mod, '__path__'):
            for path in mod.__path__:
                mod_paths.append(self._dirname_if_file(path))
        elif hasattr(mod, '__file__'):
            mod_paths.append(self._dirname_if_file(mod.__file__))
        else:
            # builtin or other module-like object that
            # doesn't have __file__; must be new
            return False
        new_path = self._dirname_if_file(filename)
        for mod_path in mod_paths:
            log.debug(
                "module already loaded? mod: %s new: %s",
                mod_path, new_path)
            if _samefile(mod_path, new_path):
                return True
        return False


def add_path(path, config=None):
    """Ensure that the path, or the root of the current package (if
    path is in a package), is in sys.path.
    """

    # FIXME add any src-looking dirs seen too... need to get config for that

    log.debug('Add path %s' % path)
    if not path:
        return []
    added = []
    parent = os.path.dirname(path)
    if (parent
        and os.path.exists(os.path.join(path, '__init__.py'))):
        added.extend(add_path(parent, config))
    elif not path in sys.path:
        log.debug("insert %s into sys.path", path)
        sys.path.insert(0, path)
        added.append(path)
    if config and config.srcDirs:
        for dirname in config.srcDirs:
            dirpath = os.path.join(path, dirname)
            if os.path.isdir(dirpath):
                sys.path.insert(0, dirpath)
                added.append(dirpath)
    return added


def remove_path(path):
    log.debug('Remove path %s' % path)
    if path in sys.path:
        sys.path.remove(path)
