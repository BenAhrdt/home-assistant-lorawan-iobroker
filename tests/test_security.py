"""Isolated regression checks; no running Home Assistant required."""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/lorawan_iobroker'


def load_nodes(filename, names, namespace):
    tree = ast.parse((ROOT / filename).read_text())
    selected = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    for node in tree.body:
        if getattr(node, 'name', None) in names or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
        ):
            selected.append(node)
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), filename, 'exec'), namespace)
    return namespace


class SecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_light_parameters_cannot_redirect_target(self):
        call = AsyncMock()
        allowed = Mock(return_value=True)
        ns = load_nodes('bridge.py', {'LIGHT_PARAMETERS', '_handle_attribute_command'}, {
            '_command_allowed_for_entity': allowed, '_call_service': call,
            'ATTR_ENTITY_ID': 'entity_id', 'LOGGER': logging.getLogger('test'),
        })
        for attribute in ('entity_id', 'device_id', 'area_id', 'floor_id', 'label_id', 'unknown', ['entity_id']):
            await ns['_handle_attribute_command'](None, None, {
                'entity_id': 'light.allowed', 'attribute': attribute, 'value': 'light.other',
            })
        call.assert_not_awaited()
        for attribute, value in (('brightness', '120'), ('rgb_color', [1, 2, 3]), ('effect', 'rainbow')):
            await ns['_handle_attribute_command'](None, None, {
                'entity_id': 'light.allowed', 'attribute': attribute, 'value': value,
            })
            self.assertEqual(call.await_args.args[3]['entity_id'], 'light.allowed')
            self.assertIn(attribute, call.await_args.args[3])
        allowed.return_value = False
        call.reset_mock()
        await ns['_handle_attribute_command'](None, SimpleNamespace(label='ToIob', source='bridge'), {
            'entity_id': 'light.other', 'attribute': 'brightness', 'value': 100,
        })
        call.assert_not_awaited()

    async def test_admin_required_before_request_body_or_side_effects(self):
        class Forbidden(Exception):
            def __init__(self, **kwargs):
                pass

        ns = load_nodes('http.py', {
            '_require_admin', 'LoRaWANOptionsView', 'LoRaWANPublishView', 'LoRaWANDataView',
        }, {'HomeAssistantView': type('View', (), {'json': staticmethod(lambda x: x)}),
            'web': SimpleNamespace(HTTPForbidden=Forbidden),
            'CONF_PERIODIC_INTERVAL_MINUTES': 'periodic_interval_minutes',
            '_entry_from_request': Mock(return_value=SimpleNamespace(options={})),
            'async_publish_periodic_message': AsyncMock(), 'integration_payload': Mock(return_value={}),
        })

        class Request(dict):
            app = {'hass': SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=Mock()))}
            json = AsyncMock(return_value={'periodic_interval_minutes': 10})

        for user in (None, SimpleNamespace(is_admin=False)):
            request = Request(hass_user=user)
            for name, method in (('LoRaWANOptionsView', 'post'), ('LoRaWANPublishView', 'post'), ('LoRaWANDataView', 'get')):
                with self.assertRaises(Forbidden):
                    await getattr(ns[name](), method)(request)
            request.json.assert_not_awaited()
        request = Request(hass_user=SimpleNamespace(is_admin=True))
        self.assertEqual(await ns['LoRaWANOptionsView']().post(request), {'ok': True, 'periodic_interval_minutes': 10})
        self.assertEqual(await ns['LoRaWANPublishView']().post(request), {'ok': True})
        ns['async_publish_periodic_message'].assert_awaited_once()
        await ns['LoRaWANDataView']().get(request)

    def test_control_route_removed_and_panel_admin_only(self):
        self.assertNotIn('LoRaWANControlView', (ROOT / 'http.py').read_text())
        self.assertNotIn('LoRaWANControlView', (ROOT / '__init__.py').read_text())
        self.assertIn('require_admin=True', (ROOT / '__init__.py').read_text())


if __name__ == '__main__':
    unittest.main()
