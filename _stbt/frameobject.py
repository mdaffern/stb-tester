"""
Copyright 2016-2018 Stb-tester.com Ltd.
License: LGPL v2.1 or (at your option) any later version (see
https://github.com/stb-tester/stb-tester/blob/master/LICENSE for details).
"""
import functools
import threading


def _memoize_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
        if fn not in self._FrameObject__frame_object_cache:
            self._FrameObject__frame_object_cache[fn] = fn(self)
        return self._FrameObject__frame_object_cache[fn]
    return inner


def _mark_in_is_visible(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
        try:
            self._FrameObject__local.in_is_visible += 1
        except AttributeError:
            self._FrameObject__local.in_is_visible = 1
        try:
            return bool(fn(self))
        finally:
            self._FrameObject__local.in_is_visible -= 1
    return inner


def _noneify_property_fn(fn):
    @functools.wraps(fn)
    def inner(self):
        # pylint: disable=protected-access
        if (getattr(self._FrameObject__local, "in_is_visible", 0) or
                self.is_visible):
            return fn(self)
        else:
            return None
    return inner


class _FrameObjectMeta(type):
    def __new__(mcs, name, parents, dct):
        for k, v in dct.iteritems():
            if isinstance(v, property):
                # Properties must not have setters
                if v.fset is not None:
                    raise Exception(
                        "FrameObjects must be immutable but this property has "
                        "a setter")
                f = v.fget
                # The value of any property is cached after the first use
                f = _memoize_property_fn(f)
                # Public properties return `None` if the FrameObject isn't
                # visible.
                if k == 'is_visible':
                    f = _mark_in_is_visible(f)
                elif not k.startswith('_'):
                    f = _noneify_property_fn(f)
                dct[k] = property(f)

        if 'AUTO_SELFTEST_EXPRESSIONS' not in dct:
            dct['AUTO_SELFTEST_EXPRESSIONS'] = ['%s(frame={frame})' % name]

        return super(_FrameObjectMeta, mcs).__new__(mcs, name, parents, dct)

    def __init__(cls, name, parents, dct):
        property_names = sorted([
            p for p in dir(cls)
            if isinstance(getattr(cls, p), property)])
        assert 'is_visible' in property_names
        cls._fields = tuple(["is_visible"] + sorted(
            x for x in property_names
            if x != "is_visible" and not x.startswith('_')))
        super(_FrameObjectMeta, cls).__init__(name, parents, dct)


class FrameObject(object):
    # pylint: disable=line-too-long
    r'''Base class for user-defined Page Objects.

    FrameObjects are Stb-tester's implementation of the *Page Object* pattern.
    A FrameObject is a class that uses Stb-tester APIs like ``stbt.match()``
    and ``stbt.ocr()`` to extract information from the screen, and it provides
    a higher-level API in the vocabulary and user-facing concepts of your own
    application.

    .. figure:: images/object-repository/frame-object-pattern.png
       :align: center

       Based on Martin Fowler's `PageObject <fowler_>`_ diagram

    Stb-tester uses a separate instance of your FrameObject class for each
    frame of video captured from the device-under-test (hence the name "Frame
    Object"). Stb-tester provides additional tooling for writing, testing,
    and maintenance of FrameObjects.

    To define your own FrameObject class:

    * Derive from ``stbt.FrameObject``.
    * Define an ``is_visible`` property (using Python's `@property`_ decorator)
      that returns True or False.
    * Define any other properties for information that you want to extract
      from the frame.
    * Pass ``self._frame`` into any image processing function you call.

    FrameObject behaviours:

    * **Truthiness:** A FrameObject instance is considered "truthy" if it is
      visible. Any other properties (apart from ``is_visible``) will return
      ``None`` if the object isn't visible.

    * **Immutability:** FrameObjects are immutable, because they represent
      information about a specific frame of video -- in other words, an
      instance of a FrameOject represents the state of the device-under-test at
      a specific point in time. If you define any methods that change the state
      of the device-under-test, they should return a new FrameObject instance
      instead of modifying ``self``.

    * **Caching:** Each property will be cached the first time is is used. This
      allows writing testcases in a natural way, while expensive operations
      like ``ocr`` will only be done once per frame.

    The FrameObject base class defines the following methods and attributes:

    * ``__init__`` -- The default constructor takes an optional frame; if the
      frame is not provided, it will grab a frame from the device-under-test.
    * ``__nonzero__`` -- Delegates to ``is_visible``. The object will only be
      considered True if it is visible.
    * ``__repr__`` -- The object's string representation includes all the
      user-defined public properties.
    * ``__hash__`` and ``__cmp__`` -- Two instances of the same ``FrameObject``
      type are considered equal if the values of all the public properties
      match, even if the underlying frame is different. All falsey FrameObjects
      of the same type are equal.
    * ``_fields`` -- A tuple containing the names of the public properties.

    Further reading:

    * The `PageObject <fowler_>`_ pattern by Martin Fowler.
    * Tutorial: `Using FrameObjects to extract information from the screen
      <tutorial_>`_. Includes a worked example, and how to run automatic
      regression tests for your FrameObjects with the tool ``stbt
      auto-selftest``.
    * Stb-tester's `Object Repository`_ GUI for creating, debugging, and
      viewing FrameObjects.

    .. _@property: https://docs.python.org/2/library/functions.html#property
    .. _fowler: https://martinfowler.com/bliki/PageObject.html
    .. _tutorial: https://stb-tester.com/tutorials/using-frame-objects-to-extract-information-from-the-screen
    .. _Object Repository: https://stb-tester.com/manual/object-repository

    | Added in v30: The ``_fields`` attribute.
    '''
    __metaclass__ = _FrameObjectMeta

    def __init__(self, frame=None):
        if frame is None:
            import stbt
            frame = stbt.get_frame()
        self.__frame_object_cache = {}
        self.__local = threading.local()
        self._frame = frame

    def __repr__(self):
        args = ", ".join(("%s=%r" % x) for x in self._iter_fields())
        return "%s(%s)" % (self.__class__.__name__, args)

    def _iter_fields(self):
        if self:
            for x in self._fields:  # pylint:disable=no-member
                yield x, getattr(self, x)
        else:
            yield "is_visible", False

    def __nonzero__(self):
        return bool(self.is_visible)

    def __cmp__(self, other):
        # pylint: disable=protected-access
        from itertools import izip_longest
        if isinstance(other, self.__class__):
            for s, o in izip_longest(self._iter_fields(), other._iter_fields()):
                v = cmp(s[1], o[1])
                if v != 0:
                    return v
            return 0
        else:
            return NotImplemented

    def __hash__(self):
        return hash(tuple(v for _, v in self._iter_fields()))

    @property
    def is_visible(self):
        raise NotImplementedError(
            "Objects deriving from FrameObject must define an is_visible "
            "property")
