def __bootstrap__():
    """ Import the code in ``noname_wrapped.not_py`` in file as our own name

    This is a simplified version of the wrapper that setuptools writes for
    dynamic libraries when installing.
    """
    import os
    import importlib.util
    import sys
    here = os.path.dirname(__file__)
    filepath = os.path.join(here, 'noname_wrapped.not_py')
    spec = importlib.util.spec_from_file_location(__name__, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[__name__] = module
    spec.loader.exec_module(module)

__bootstrap__()
