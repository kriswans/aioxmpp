########################################################################
# File name: test_callbacks.py
# This file is part of: aioxmpp
#
# LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/>.
#
########################################################################
import asyncio
import contextlib
import functools
import unittest
import unittest.mock

from aioxmpp.callbacks import (
    TagDispatcher,
    TagListener,
    AsyncTagListener,
    OneshotTagListener,
    OneshotAsyncTagListener,
    FutureListener,
    Signal,
    AdHocSignal,
    SyncAdHocSignal,
    SyncSignal,
    Filter,
)

from aioxmpp.testutils import run_coroutine, CoroutineMock


class TestTagListener(unittest.TestCase):
    def test_data(self):
        ondata = unittest.mock.Mock()

        obj = object()

        listener = TagListener(ondata=ondata)
        listener.data(obj)
        ondata.assert_called_once_with(obj)

    def test_uninitialized_error(self):
        ondata = unittest.mock.Mock()

        listener = TagListener(ondata=ondata)
        listener.error(ValueError())

    def test_error(self):
        ondata = unittest.mock.Mock()
        onerror = unittest.mock.Mock()

        exc = ValueError()

        listener = TagListener(ondata, onerror)
        listener.error(exc)

        ondata.assert_not_called()
        onerror.assert_called_once_with(exc)

    def test_is_valid(self):
        self.assertTrue(TagListener(ondata=unittest.mock.Mock()))


class TestTagDispatcher(unittest.TestCase):
    def test_add_callback(self):
        mock = unittest.mock.Mock()

        nh = TagDispatcher()
        nh.add_callback("tag", mock)
        with self.assertRaisesRegex(ValueError,
                                     "only one listener is allowed"):
            nh.add_callback("tag", mock)

    def test_add_listener(self):
        mock = unittest.mock.Mock()

        l = TagListener(mock)

        nh = TagDispatcher()
        nh.add_listener("tag", l)
        with self.assertRaisesRegex(ValueError,
                                     "only one listener is allowed"):
            nh.add_listener("tag", l)

    def test_add_listener_skips_invalid(self):
        mock = unittest.mock.Mock()

        l1 = unittest.mock.Mock()
        l1.is_valid.return_value = True

        l2 = TagListener(mock)

        nh = TagDispatcher()
        nh.add_listener("tag", l1)
        l1.is_valid.return_value = False
        nh.add_listener("tag", l2)

        obj = object()
        nh.unicast("tag", obj)
        self.assertSequenceEqual(
            [
                unittest.mock.call.is_valid(),
            ],
            l1.mock_calls
        )

        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
            ],
            mock.mock_calls
        )

    @unittest.mock.patch("aioxmpp.callbacks.AsyncTagListener")
    def test_add_callback_async(self, AsyncTagListener):
        AsyncTagListener().is_valid.return_value = True
        AsyncTagListener.mock_calls.clear()

        data = unittest.mock.Mock()
        loop = unittest.mock.Mock()
        obj = object()

        nh = TagDispatcher()
        nh.add_callback_async("tag", data, loop=loop)

        self.assertSequenceEqual(
            [
                unittest.mock.call(data, loop=loop)
            ],
            AsyncTagListener.mock_calls
        )
        del AsyncTagListener.mock_calls[:]

        nh.unicast("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call().is_valid(),
                unittest.mock.call().data(obj),
                unittest.mock.call().data().__bool__(),
            ],
            AsyncTagListener.mock_calls
        )

    def test_add_future(self):
        mock = unittest.mock.Mock()
        mock.done.return_value = False
        obj = object()

        nh = TagDispatcher()
        nh.add_future("tag", mock)
        nh.unicast("tag", obj)
        with self.assertRaises(KeyError):
            # futures must be oneshots
            nh.unicast("tag", obj)

        nh.add_future("tag", mock)
        nh.broadcast_error(obj)
        with self.assertRaises(KeyError):
            # futures must be oneshots
            nh.unicast("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call.done(),
                unittest.mock.call.set_result(obj),
                unittest.mock.call.done(),
                unittest.mock.call.set_exception(obj),
            ],
            mock.mock_calls
        )

    def test_unicast(self):
        mock = unittest.mock.Mock()
        mock.return_value = False
        obj = object()

        nh = TagDispatcher()
        nh.add_callback("tag", mock)
        nh.unicast("tag", obj)
        nh.unicast("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
                unittest.mock.call(obj),
            ],
            mock.mock_calls
        )

    def test_unicast_fails_for_nonexistent(self):
        obj = object()
        nh = TagDispatcher()
        with self.assertRaises(KeyError):
            nh.unicast("tag", obj)

    def test_unicast_fails_for_invalid(self):
        obj = object()
        l = unittest.mock.Mock()
        l.is_valid.return_value = False
        nh = TagDispatcher()
        nh.add_listener("tag", l)
        with self.assertRaises(KeyError):
            nh.unicast("tag", obj)

    def test_unicast_to_oneshot(self):
        mock = unittest.mock.Mock()
        obj = object()

        l = OneshotTagListener(mock)

        nh = TagDispatcher()
        nh.add_listener("tag", l)

        nh.unicast("tag", obj)
        with self.assertRaises(KeyError):
            nh.unicast("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call(obj)
            ],
            mock.mock_calls
        )

    def test_unicast_removes_for_true_result(self):
        mock = unittest.mock.Mock()
        mock.return_value = True
        obj = object()

        nh = TagDispatcher()
        nh.add_callback("tag", mock)
        nh.unicast("tag", obj)
        with self.assertRaises(KeyError):
            nh.unicast("tag", obj)

        mock.assert_called_once_with(obj)

    def test_broadcast_error_to_oneshot(self):
        data = unittest.mock.Mock()
        error = unittest.mock.Mock()
        obj = object()

        l = OneshotTagListener(data, error)

        nh = TagDispatcher()
        nh.add_listener("tag", l)

        nh.broadcast_error(obj)
        with self.assertRaises(KeyError):
            nh.unicast("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call(obj)
            ],
            error.mock_calls
        )
        self.assertFalse(data.mock_calls)

    def test_broadcast_error_skip_invalid(self):
        obj = object()
        l = unittest.mock.Mock()
        l.is_valid.return_value = False
        nh = TagDispatcher()
        nh.add_listener("tag", l)
        nh.broadcast_error(obj)
        self.assertSequenceEqual(
            [
                unittest.mock.call.is_valid()
            ],
            l.mock_calls
        )

    def test_remove_listener(self):
        mock = unittest.mock.Mock()
        nh = TagDispatcher()
        nh.add_callback("tag", mock)
        nh.remove_listener("tag")
        with self.assertRaises(KeyError):
            nh.unicast("tag", object())
        mock.assert_not_called()

    def test_broadcast_error(self):
        data = unittest.mock.Mock()
        error1 = unittest.mock.Mock()
        error1.return_value = False
        error2 = unittest.mock.Mock()
        error2.return_value = False

        l1 = TagListener(data, error1)
        l2 = TagListener(data, error2)

        obj = object()

        nh = TagDispatcher()
        nh.add_listener("tag1", l1)
        nh.add_listener("tag2", l2)

        nh.broadcast_error(obj)
        nh.broadcast_error(obj)

        data.assert_not_called()
        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
                unittest.mock.call(obj),
            ],
            error1.mock_calls
        )
        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
                unittest.mock.call(obj),
            ],
            error2.mock_calls
        )

    def test_broadcast_error_removes_on_true_result(self):
        data = unittest.mock.Mock()
        error1 = unittest.mock.Mock()
        error1.return_value = True

        l1 = TagListener(data, error1)

        obj = object()

        nh = TagDispatcher()
        nh.add_listener("tag1", l1)

        nh.broadcast_error(obj)
        nh.broadcast_error(obj)

        data.assert_not_called()
        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
            ],
            error1.mock_calls
        )

    def test_unicast_error(self):
        data = unittest.mock.Mock()
        error1 = unittest.mock.Mock()
        error1.return_value = False
        error2 = unittest.mock.Mock()
        error2.return_value = False

        l1 = TagListener(data, error1)
        l2 = TagListener(data, error2)

        obj = object()

        nh = TagDispatcher()
        nh.add_listener("tag1", l1)
        nh.add_listener("tag2", l2)

        nh.unicast_error("tag1", obj)

        data.assert_not_called()
        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
            ],
            error1.mock_calls
        )
        self.assertSequenceEqual(
            [
            ],
            error2.mock_calls
        )

    def test_unicast_error_skip_and_remove_invalid_and_raise_KeyError(self):
        obj = object()
        l = unittest.mock.Mock()
        l.is_valid.return_value = False
        nh = TagDispatcher()
        nh.add_listener("tag", l)
        with self.assertRaises(KeyError):
            nh.unicast_error("tag", obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call.is_valid()
            ],
            l.mock_calls
        )

    def test_unicast_error_removes_on_true_result(self):
        data = unittest.mock.Mock()
        error1 = unittest.mock.Mock()
        error1.return_value = True

        l1 = TagListener(data, error1)

        obj = object()

        nh = TagDispatcher()
        nh.add_listener("tag1", l1)

        nh.unicast_error("tag1", obj)
        with self.assertRaises(KeyError):
            nh.unicast_error("tag1", obj)

        data.assert_not_called()
        self.assertSequenceEqual(
            [
                unittest.mock.call(obj),
            ],
            error1.mock_calls
        )

    def test_close(self):
        data = unittest.mock.Mock()
        error1 = unittest.mock.Mock()
        error2 = unittest.mock.Mock()

        l1 = TagListener(data, error1)
        l2 = TagListener(data, error2)

        obj = object()

        nh = TagDispatcher()
        nh.add_listener("tag1", l1)
        nh.add_listener("tag2", l2)

        nh.close_all(obj)

        data.assert_not_called()
        error1.assert_called_once_with(obj)
        error2.assert_called_once_with(obj)

        with self.assertRaises(KeyError):
            nh.remove_listener("tag1")
        with self.assertRaises(KeyError):
            nh.remove_listener("tag2")
        with self.assertRaises(KeyError):
            nh.unicast("tag1", None)
        with self.assertRaises(KeyError):
            nh.unicast("tag2", None)


class TestAsyncTagListener(unittest.TestCase):
    def test_everything(self):
        data = unittest.mock.MagicMock()
        error = unittest.mock.MagicMock()
        loop = unittest.mock.MagicMock()
        obj = object()
        tl = AsyncTagListener(data, error, loop=loop)
        self.assertFalse(tl.data(obj))
        self.assertFalse(tl.error(obj))

        self.assertFalse(data.mock_calls)
        self.assertFalse(error.mock_calls)
        self.assertSequenceEqual(
            [
                unittest.mock.call.__bool__(),
                unittest.mock.call.call_soon(data, obj),
                unittest.mock.call.call_soon(error, obj),
            ],
            loop.mock_calls
        )


class TestOneshotAsyncTagListener(unittest.TestCase):
    def test_everything(self):
        data = unittest.mock.MagicMock()
        error = unittest.mock.MagicMock()
        loop = unittest.mock.MagicMock()
        obj = object()
        tl = OneshotAsyncTagListener(data, error, loop=loop)
        self.assertTrue(tl.data(obj))
        self.assertTrue(tl.error(obj))

        self.assertFalse(data.mock_calls)
        self.assertFalse(error.mock_calls)
        self.assertSequenceEqual(
            [
                unittest.mock.call.__bool__(),
                unittest.mock.call.call_soon(data, obj),
                unittest.mock.call.call_soon(error, obj),
            ],
            loop.mock_calls
        )


class TestFutureListener(unittest.TestCase):
    def test_normal_operation(self):
        loop = asyncio.get_event_loop()
        fut = asyncio.Future(loop=loop)
        obj = object()
        tl = FutureListener(fut)

        self.assertTrue(tl.is_valid())

        self.assertTrue(tl.data(obj))
        self.assertEqual(fut.result(), obj)

        self.assertFalse(tl.is_valid())

    def test_error_dispatch(self):
        loop = asyncio.get_event_loop()
        fut = asyncio.Future(loop=loop)
        obj = Exception()
        tl = FutureListener(fut)

        self.assertTrue(tl.is_valid())

        self.assertTrue(tl.error(obj))
        self.assertEqual(fut.exception(), obj)

        self.assertFalse(tl.is_valid())

    def test_signals_non_existance_with_cancelled_future(self):
        loop = asyncio.get_event_loop()
        fut = asyncio.Future(loop=loop)
        tl = FutureListener(fut)

        self.assertTrue(tl.is_valid())

        fut.cancel()

        self.assertFalse(tl.is_valid())

    def test_swallow_invalid_state_error(self):
        loop = asyncio.get_event_loop()
        fut = asyncio.Future(loop=loop)
        obj = object()
        tl = FutureListener(fut)

        fut.cancel()

        self.assertTrue(tl.data(obj))
        self.assertTrue(tl.error(obj))


class TestAdHocSignal(unittest.TestCase):
    def test_STRONG_rejects_non_callable(self):
        signal = AdHocSignal()
        with self.assertRaisesRegex(TypeError, "must be callable"):
            signal.STRONG(object())

    def test_WEAK_rejects_non_callable(self):
        signal = AdHocSignal()
        with self.assertRaisesRegex(TypeError, "must be callable"):
            signal.WEAK(object())

    def test_ASYNC_WITH_LOOP_rejects_non_callable(self):
        signal = AdHocSignal()
        with self.assertRaisesRegex(TypeError, "must be callable"):
            signal.ASYNC_WITH_LOOP(asyncio.get_event_loop())(object())

    def test_connect_and_fire(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        signal.connect(fun)

        signal.fire()
        signal.fire()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

    def test_connect_and_call(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        signal.connect(fun)

        signal()

        fun.assert_called_once_with()

    def test_connect_weak_uses_weakref(self):
        signal = AdHocSignal()

        with unittest.mock.patch("weakref.ref") as ref:
            fun = unittest.mock.MagicMock()
            signal.connect(fun, AdHocSignal.WEAK)
            ref.assert_called_once_with(fun)

    def test_connect_weak_uses_WeakMethod_for_methods(self):
        signal = AdHocSignal()

        class Foo:
            def meth(self):
                return None

        f = Foo()

        with unittest.mock.patch("weakref.WeakMethod") as ref:
            signal.connect(f.meth, AdHocSignal.WEAK)

        ref.assert_called_once_with(f.meth)

    def test_connect_does_not_use_weakref(self):
        signal = AdHocSignal()

        with unittest.mock.patch("weakref.ref") as ref:
            fun = unittest.mock.MagicMock()
            signal.connect(fun)
            self.assertFalse(ref.mock_calls)

    @unittest.mock.patch("weakref.ref")
    def test_fire_removes_stale_references(self, ref):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None
        ref().return_value = None

        signal.connect(fun, AdHocSignal.WEAK)

        signal.fire()

        self.assertFalse(signal._connections)

    def test_connect_async(self):
        signal = AdHocSignal()

        mock = unittest.mock.MagicMock()
        fun = functools.partial(mock)

        signal.connect(fun, AdHocSignal.ASYNC_WITH_LOOP(None))
        signal.fire()

        mock.assert_not_called()

        run_coroutine(asyncio.sleep(0))

        mock.assert_called_once_with()

    def test_connect_spawn(self):
        signal = AdHocSignal()

        mock = CoroutineMock()

        @asyncio.coroutine
        def coro(*args, **kwargs):
            yield from mock(*args, **kwargs)

        signal.connect(coro, AdHocSignal.SPAWN_WITH_LOOP(None))
        signal.fire("a", 1, b="c")

        self.assertSequenceEqual(mock.mock_calls, [])

        run_coroutine(asyncio.sleep(0))

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call("a", 1, b="c")
            ]
        )

    def test_connect_spawn_emits_always(self):
        signal = AdHocSignal()

        mock = CoroutineMock()

        @asyncio.coroutine
        def coro(*args, **kwargs):
            yield from mock(*args, **kwargs)

        signal.connect(coro, AdHocSignal.SPAWN_WITH_LOOP(None))
        signal.fire("a", 1, b="c")
        signal.fire("x")

        self.assertSequenceEqual(mock.mock_calls, [])

        run_coroutine(asyncio.sleep(0))

        run_coroutine(asyncio.sleep(0))

        self.assertSequenceEqual(
            mock.mock_calls,
            [
                unittest.mock.call("a", 1, b="c"),
                unittest.mock.call("x"),
            ]
        )

    def test_SPAWN_rejects_non_coroutine(self):
        def fun():
            pass

        signal = AdHocSignal()

        with self.assertRaisesRegex(TypeError, "must be coroutine"):
            signal.SPAWN_WITH_LOOP(None)(fun)

    def test_fire_with_arguments(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()

        signal.connect(fun)

        signal("a", 1, foo=None)

        fun.assert_called_once_with("a", 1, foo=None)

    def test_remove_callback_on_true_result(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = True

        signal.connect(fun)

        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

    def test_remove_by_token(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        token = signal.connect(fun)

        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

        signal.disconnect(token)

        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call(),
                unittest.mock.call(),
            ],
            fun.mock_calls
        )

    def test_disconnect_is_idempotent(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        token = signal.connect(fun)

        signal.disconnect(token)
        signal.disconnect(token)

    def test_context_connect(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        with signal.context_connect(fun):
            signal("foo")
        signal("bar")
        with signal.context_connect(fun) as token:
            signal("baz")
            signal.disconnect(token)
            signal("fnord")

        self.assertSequenceEqual(
            [
                unittest.mock.call("foo"),
                unittest.mock.call("baz"),
            ],
            fun.mock_calls
        )

    def test_context_connect_forwards_exceptions_and_disconnects(self):
        signal = AdHocSignal()

        fun = unittest.mock.MagicMock()
        fun.return_value = None

        exc = ValueError()
        with self.assertRaises(ValueError) as ctx:
            with signal.context_connect(fun):
                signal("foo")
                raise exc
        signal("bar")

        self.assertIs(exc, ctx.exception)

        self.assertSequenceEqual(
            [
                unittest.mock.call("foo"),
            ],
            fun.mock_calls
        )

    def test_connect_auto_future_uses_set_result_with_None(self):
        signal = AdHocSignal()

        fut = unittest.mock.Mock()
        fut.done.return_value = False

        signal.connect(fut, AdHocSignal.AUTO_FUTURE)

        signal()
        signal()

        self.assertSequenceEqual(
            [
                unittest.mock.call.done(),
                unittest.mock.call.set_result(None)
            ],
            fut.mock_calls
        )

    def test_connect_auto_future_uses_set_result_with_argument(self):
        signal = AdHocSignal()

        obj = object()

        fut = unittest.mock.Mock()
        fut.done.return_value = False

        signal.connect(fut, AdHocSignal.AUTO_FUTURE)

        signal(obj)
        signal(obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call.done(),
                unittest.mock.call.set_result(obj)
            ],
            fut.mock_calls
        )

    def test_connect_auto_future_fails_if_more_than_one_argument(self):
        fut = unittest.mock.Mock()
        fut.done.return_value = False

        obj = object()

        wrapped = AdHocSignal.AUTO_FUTURE(fut)

        with self.assertRaises(TypeError):
            wrapped(obj, "foo")

        with self.assertRaises(TypeError):
            wrapped(obj, fnord="foo")

    def test_connect_auto_future_converts_exceptions(self):
        signal = AdHocSignal()

        obj = ValueError()

        fut = unittest.mock.Mock()
        fut.done.return_value = False

        signal.connect(fut, AdHocSignal.AUTO_FUTURE)

        signal(obj)
        signal(obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call.done(),
                unittest.mock.call.set_exception(obj)
            ],
            fut.mock_calls
        )

    def test_connect_skips_if_future_is_done(self):
        signal = AdHocSignal()

        obj = ValueError()

        fut = unittest.mock.Mock()
        fut.done.return_value = True

        signal.connect(fut, AdHocSignal.AUTO_FUTURE)

        signal("foo")
        signal(obj)

        self.assertSequenceEqual(
            [
                unittest.mock.call.done(),
            ],
            fut.mock_calls
        )

    def test_logger_on_connect(self):
        logger = unittest.mock.Mock()
        signal = AdHocSignal()
        signal.logger = logger

        a = unittest.mock.Mock()
        signal.connect(a)

        logger.debug.assert_called_with(
            "connecting %r with mode %r",
            a, signal.STRONG)

    def test_logger_on_emit_with_exception(self):
        logger = unittest.mock.Mock()
        signal = AdHocSignal()
        signal.logger = logger

        a = unittest.mock.Mock()
        signal.connect(a)

        a.side_effect = Exception()

        signal()

        logger.exception.assert_called_with(
            "listener attached to signal raised"
        )

    def test_full_isolation(self):
        signal = AdHocSignal()

        base = unittest.mock.Mock()

        base.a.return_value = None
        base.a.side_effect = OSError()

        base.b.return_value = None
        base.b.side_effect = Exception()

        base.c.return_value = None

        base.d.return_value = None
        base.d.side_effect = ValueError()

        signal.connect(base.a)
        signal.connect(base.b)
        signal.connect(base.c)
        signal.connect(base.d)

        signal()

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.a(),
                unittest.mock.call.b(),
                unittest.mock.call.c(),
                unittest.mock.call.d(),
            ]
        )

        signal()

        self.assertSequenceEqual(
            base.mock_calls,
            [
                unittest.mock.call.a(),
                unittest.mock.call.b(),
                unittest.mock.call.c(),
                unittest.mock.call.d(),
                unittest.mock.call.c(),
            ]
        )

    def test_future(self):
        signal = AdHocSignal()

        with contextlib.ExitStack() as stack:
            Future = stack.enter_context(
                unittest.mock.patch("asyncio.Future")
            )

            connect = stack.enter_context(
                unittest.mock.patch.object(
                    signal,
                    "connect"
                )
            )

            fut = signal.future()

        self.assertSequenceEqual(
            Future.mock_calls,
            [
                unittest.mock.call.Future()
            ]
        )

        self.assertSequenceEqual(
            connect.mock_calls,
            [
                unittest.mock.call(
                    Future(),
                    signal.AUTO_FUTURE,
                ),
            ]
        )

        self.assertEqual(fut, Future())


class TestSyncAdHocSignal(unittest.TestCase):
    def test_connect_and_fire(self):
        coro = CoroutineMock()
        coro.return_value = True

        signal = SyncAdHocSignal()
        signal.connect(coro)

        run_coroutine(signal.fire(1, 2, foo="bar"))

        self.assertSequenceEqual(
            [
                unittest.mock.call(1, 2, foo="bar"),
            ],
            coro.mock_calls
        )

    def test_fire_removes_on_false_result(self):
        coro = CoroutineMock()
        coro.return_value = False

        signal = SyncAdHocSignal()
        signal.connect(coro)

        run_coroutine(signal.fire(1, 2, foo="bar"))

        self.assertSequenceEqual(
            [
                unittest.mock.call(1, 2, foo="bar"),
            ],
            coro.mock_calls
        )
        coro.reset_mock()

        run_coroutine(signal.fire(1, 2, foo="bar"))

        self.assertSequenceEqual(
            [
            ],
            coro.mock_calls
        )

    def test_ordered_calls(self):
        calls = []

        def make_coro(i):
            @asyncio.coroutine
            def coro():
                nonlocal calls
                calls.append(i)
            return coro

        coros = [make_coro(i) for i in range(3)]

        signal = SyncAdHocSignal()
        for coro in reversed(coros):
            signal.connect(coro)

        run_coroutine(signal.fire())

        self.assertSequenceEqual(
            [2, 1, 0],
            calls
        )

    def test_context_connect(self):
        signal = SyncAdHocSignal()

        coro = CoroutineMock()
        coro.return_value = True

        with signal.context_connect(coro):
            run_coroutine(signal("foo"))
        run_coroutine(signal("bar"))
        with signal.context_connect(coro) as token:
            run_coroutine(signal("baz"))
            signal.disconnect(token)
            run_coroutine(signal("fnord"))

        self.assertSequenceEqual(
            [
                unittest.mock.call("foo"),
                unittest.mock.call("baz"),
            ],
            coro.mock_calls
        )


class TestSignal(unittest.TestCase):
    def test_get(self):
        class Foo:
            s = Signal()

        instance1 = Foo()
        instance2 = Foo()

        self.assertIsNot(instance1.s, instance2.s)
        self.assertIs(instance1.s, instance1.s)
        self.assertIs(instance2.s, instance2.s)

        self.assertIsInstance(instance1.s, AdHocSignal)
        self.assertIsInstance(instance2.s, AdHocSignal)

    def test_reject_set(self):
        class Foo:
            s = Signal()

        instance = Foo()

        with self.assertRaises(AttributeError):
            instance.s = "foo"

    def test_reject_delete(self):
        class Foo:
            s = Signal()

        instance = Foo()

        with self.assertRaises(AttributeError):
            del instance.s

    def test_default_docstring(self):
        class Foo:
            s = Signal()

        self.assertIsNone(Foo.s.__doc__)

    def test_set_docstring(self):
        class Foo:
            s = Signal(doc=unittest.mock.sentinel.doc)

        self.assertIs(Foo.s.__doc__, unittest.mock.sentinel.doc)


class TestSyncSignal(unittest.TestCase):
    def test_get(self):
        class Foo:
            s = SyncSignal()

        instance1 = Foo()
        instance2 = Foo()

        self.assertIsNot(instance1.s, instance2.s)
        self.assertIs(instance1.s, instance1.s)
        self.assertIs(instance2.s, instance2.s)

        self.assertIsInstance(instance1.s, SyncAdHocSignal)
        self.assertIsInstance(instance2.s, SyncAdHocSignal)

    def test_reject_set(self):
        class Foo:
            s = SyncSignal()

        instance = Foo()

        with self.assertRaises(AttributeError):
            instance.s = "foo"

    def test_reject_delete(self):
        class Foo:
            s = SyncSignal()

        instance = Foo()

        with self.assertRaises(AttributeError):
            del instance.s

    def test_default_docstring(self):
        class Foo:
            s = SyncSignal()

        self.assertIsNone(Foo.s.__doc__)

    def test_set_docstring(self):
        class Foo:
            s = SyncSignal(doc=unittest.mock.sentinel.doc)

        self.assertIs(Foo.s.__doc__, unittest.mock.sentinel.doc)


class TestFilter_Token(unittest.TestCase):
    def test_each_is_unique(self):
        t1 = Filter.Token()
        t2 = Filter.Token()
        self.assertIsNot(t1, t2)
        self.assertNotEqual(t1, t2)

    def test_str(self):
        self.assertRegex(
            str(Filter.Token()),
            r"<[a-zA-Z._]+\.Filter\.Token 0x[0-9a-f]+>"
        )


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.f = Filter()

    def tearDown(self):
        del self.f

    def test_register(self):
        func = unittest.mock.Mock()
        func.return_value = None

        token = self.f.register(func, 0)
        self.assertIsNotNone(token)

    def test_filter_passes_args(self):
        func = unittest.mock.Mock()
        func.return_value = None

        self.f.register(func, 0)

        iq = unittest.mock.sentinel.iq

        self.assertIsNone(self.f.filter(
            iq,
            unittest.mock.sentinel.foo,
            bar=unittest.mock.sentinel.bar,
        ))
        self.assertSequenceEqual(
            [
                unittest.mock.call(
                    iq,
                    unittest.mock.sentinel.foo,
                    bar=unittest.mock.sentinel.bar,
                ),
            ],
            func.mock_calls
        )

    def test_filter_chain(self):
        mock = unittest.mock.Mock()

        self.f.register(mock.func1, 0)
        self.f.register(mock.func2, 0)

        result = self.f.filter(
            mock.stanza,
            unittest.mock.sentinel.foo,
            unittest.mock.sentinel.bar,
            fnord=unittest.mock.sentinel.fnord,
        )

        calls = list(mock.mock_calls)

        self.assertEqual(
            mock.func2(),
            result
        )
        self.assertSequenceEqual(
            [
                unittest.mock.call.func1(
                    mock.stanza,
                    unittest.mock.sentinel.foo,
                    unittest.mock.sentinel.bar,
                    fnord=unittest.mock.sentinel.fnord,
                ),
                unittest.mock.call.func2(
                    mock.func1(),
                    unittest.mock.sentinel.foo,
                    unittest.mock.sentinel.bar,
                    fnord=unittest.mock.sentinel.fnord,
                ),
            ],
            calls
        )

    def test_filter_chain_aborts_on_None_result(self):
        mock = unittest.mock.Mock()

        mock.func2.return_value = None

        self.f.register(mock.func1, 0)
        self.f.register(mock.func2, 0)
        self.f.register(mock.func3, 0)

        result = self.f.filter(
            mock.stanza,
            unittest.mock.sentinel.foo,
            unittest.mock.sentinel.bar,
            fnord=unittest.mock.sentinel.fnord,
        )

        calls = list(mock.mock_calls)

        self.assertIsNone(result)
        self.assertSequenceEqual(
            [
                unittest.mock.call.func1(
                    mock.stanza,
                    unittest.mock.sentinel.foo,
                    unittest.mock.sentinel.bar,
                    fnord=unittest.mock.sentinel.fnord,
                ),
                unittest.mock.call.func2(
                    mock.func1(),
                    unittest.mock.sentinel.foo,
                    unittest.mock.sentinel.bar,
                    fnord=unittest.mock.sentinel.fnord,
                ),
            ],
            calls
        )

    def test_unregister_by_token(self):
        func = unittest.mock.Mock()
        token = self.f.register(func, 0)
        self.f.unregister(token)
        self.f.filter(object())
        self.assertFalse(func.mock_calls)

    def test_unregister_raises_ValueError_if_token_not_found(self):
        with self.assertRaisesRegex(ValueError, "unregistered token"):
            self.f.unregister(object())

    def test_register_with_order(self):
        mock = unittest.mock.Mock()

        self.f.register(mock.func1, 1)
        self.f.register(mock.func2, 0)
        self.f.register(mock.func3, -1)

        result = self.f.filter(mock.stanza)
        calls = list(mock.mock_calls)

        self.assertEqual(
            mock.func1(),
            result
        )
        self.assertSequenceEqual(
            [
                unittest.mock.call.func3(mock.stanza),
                unittest.mock.call.func2(mock.func3()),
                unittest.mock.call.func1(mock.func2()),
            ],
            calls
        )

    def test_context_register_is_context_manager(self):
        cm = self.f.context_register(
            unittest.mock.sentinel.func,
            unittest.mock.sentinel.order,
        )
        self.assertTrue(
            hasattr(cm, "__enter__")
        )
        self.assertTrue(
            hasattr(cm, "__exit__")
        )

    def test_context_register_enter_registers_filter(self):
        with contextlib.ExitStack() as stack:
            register = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "register",
            ))
            register.return_value = unittest.mock.sentinel.token
            stack.enter_context(unittest.mock.patch.object(
                self.f,
                "unregister",
            ))

            cm = self.f.context_register(
                unittest.mock.sentinel.func,
                unittest.mock.sentinel.order
            )
            register.assert_not_called()
            cm.__enter__()

            register.assert_called_with(
                unittest.mock.sentinel.func,
                unittest.mock.sentinel.order,
            )

            cm.__exit__(None, None, None)

    def test_context_register_enter_registers_filter_without_order_if_order_not_passed(self):  # NOQA
        with contextlib.ExitStack() as stack:
            register = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "register",
            ))
            register.return_value = unittest.mock.sentinel.token
            stack.enter_context(unittest.mock.patch.object(
                self.f,
                "unregister",
            ))

            cm = self.f.context_register(
                unittest.mock.sentinel.func,
            )
            register.assert_not_called()
            cm.__enter__()

            register.assert_called_with(
                unittest.mock.sentinel.func,
            )

            cm.__exit__(None, None, None)

    def test_context_register_exit_unregisters_filter(self):
        with contextlib.ExitStack() as stack:
            register = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "register",
            ))
            register.return_value = unittest.mock.sentinel.token
            unregister = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "unregister",
            ))

            cm = self.f.context_register(
                unittest.mock.sentinel.func,
                unittest.mock.sentinel.order,
            )

            cm.__enter__()
            unregister.assert_not_called()

            cm.__exit__(None, None, None)
            unregister.assert_called_once_with(
                unittest.mock.sentinel.token
            )

    def test_context_register_unregisters_also_on_exception(self):
        class FooException(Exception):
            pass

        with contextlib.ExitStack() as stack:
            register = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "register",
            ))
            register.return_value = unittest.mock.sentinel.token
            unregister = stack.enter_context(unittest.mock.patch.object(
                self.f,
                "unregister",
            ))

            stack.enter_context(self.assertRaises(FooException))

            cm = self.f.context_register(
                unittest.mock.sentinel.func,
                unittest.mock.sentinel.order,
            )

            stack.enter_context(cm)

            raise FooException()

        unregister.assert_called_once_with(
            unittest.mock.sentinel.token
        )
