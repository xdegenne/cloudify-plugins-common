########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.


import testtools

from mock import patch

from cloudify import ctx as ctx_proxy
from cloudify import manager
from cloudify import decorators
from cloudify.decorators import operation, workflow
from cloudify import context
from cloudify.exceptions import NonRecoverableError, ProcessExecutionError
from cloudify.workflows import workflow_context

import cloudify.tests.mocks.mock_rest_client as rest_client_mock


class MockNotPicklableException(Exception):
    """Non-picklable exception"""
    def __init__(self, custom_error):
        self.message = custom_error

    def __str__(self):
        return self.message


class MockPicklableException(Exception):
    """Non-picklable exception"""
    def __init__(self, custom_error):
        super(Exception, self).__init__(custom_error)


@operation
def acquire_context(a, b, ctx, **kwargs):
    return ctx


@operation
def some_operation(**kwargs):
    from cloudify import ctx
    return ctx


@workflow
def error_workflow(ctx, picklable=False, **_):
    if picklable:
        raise MockPicklableException('hello world!')
    raise MockNotPicklableException('hello world!')


class OperationTest(testtools.TestCase):

    def test_empty_ctx(self):
        ctx = acquire_context(0, 0)
        self.assertIsInstance(ctx, context.CloudifyContext)

    def test_provided_ctx(self):
        ctx = {'node_id': '1234'}
        kwargs = {'__cloudify_context': ctx}
        ctx = acquire_context(0, 0, **kwargs)
        self.assertIsInstance(ctx, context.CloudifyContext)
        self.assertEquals('1234', ctx.instance.id)

    def test_proxied_ctx(self):

        self.assertRaises(RuntimeError,
                          lambda: ctx_proxy.instance.id)

        @operation
        def test_op(ctx, **kwargs):
            self.assertEqual(ctx, ctx_proxy)

        test_op()

        self.assertRaises(RuntimeError,
                          lambda: ctx_proxy.instance.id)

    def test_provided_capabilities(self):
        ctx = {
            'node_id': '5678',
        }

        # using a mock rest client
        manager.get_rest_client = \
            lambda: rest_client_mock.MockRestclient()

        rest_client_mock.put_node_instance(
            '5678',
            relationships=[{'target_id': 'some_node',
                            'target_name': 'some_node'}])
        rest_client_mock.put_node_instance('some_node',
                                           runtime_properties={'k': 'v'})

        kwargs = {'__cloudify_context': ctx}
        ctx = acquire_context(0, 0, **kwargs)
        self.assertIn('k', ctx.capabilities)
        self.assertEquals('v', ctx.capabilities['k'])

    def test_capabilities_clash(self):
        ctx = {
            'node_id': '5678',
        }

        # using a mock rest client
        manager.get_rest_client = \
            lambda: rest_client_mock.MockRestclient()

        rest_client_mock.put_node_instance(
            '5678',
            relationships=[{'target_id': 'node1',
                            'target_name': 'node1'},
                           {'target_id': 'node2',
                            'target_name': 'node2'}])

        rest_client_mock.put_node_instance('node1',
                                           runtime_properties={'k': 'v1'})
        rest_client_mock.put_node_instance('node2',
                                           runtime_properties={'k': 'v2'})

        kwargs = {'__cloudify_context': ctx}
        ctx = acquire_context(0, 0, **kwargs)
        self.assertRaises(NonRecoverableError, ctx.capabilities.__contains__,
                          'k')

    def test_workflow_error_delegation(self):
        try:
            workflow_context.get_rest_client = \
                lambda: rest_client_mock.MockRestclient()
            decorators.get_rest_client = \
                lambda: rest_client_mock.MockRestclient()
            manager.get_rest_client = \
                lambda: rest_client_mock.MockRestclient()
            kwargs = {'__cloudify_context': {}}
            try:
                error_workflow(picklable=False, **kwargs)
                self.fail('Expected exception')
            except ProcessExecutionError as e:
                self.assertTrue('hello world!' in e.message)
                self.assertTrue('test_decorators.py' in e.traceback)
                self.assertTrue(MockNotPicklableException.__name__ in
                                e.error_type)
            try:
                error_workflow(picklable=True, **kwargs)
                self.fail('Expected exception')
            except ProcessExecutionError as e:
                self.assertTrue('hello world!' in e.message)
                self.assertTrue('test_decorators.py' in e.traceback)
                self.assertTrue(MockPicklableException.__name__ in
                                e.error_type)
        finally:
            from cloudify.workflows import api
            api.ctx = None
            api.pipe = None

    def test_instance_update(self):
        with patch.object(context.NodeInstanceContext,
                          'update') as mock_update:
            kwargs = {'__cloudify_context': {
                'node_id': '5678'
            }}
            some_operation(**kwargs)
            mock_update.assert_called_once_with()

    def test_source_target_update_in_relationship(self):
        with patch.object(context.NodeInstanceContext,
                          'update') as mock_update:
            kwargs = {'__cloudify_context': {
                'node_id': '5678',
                'relationships': ['1111'],
                'related': {
                    'node_id': '1111',
                    'is_target': True
                }
            }}
            some_operation(**kwargs)
            self.assertEqual(2, mock_update.call_count)
