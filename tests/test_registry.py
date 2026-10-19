"""Verify device grouping and the single entity traversal per request."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from test_security import load_nodes


class RegistryTests(unittest.TestCase):
    def test_index_preserves_grouping_across_sources(self):
        entities = Mock()
        entities.values.return_value = [
            SimpleNamespace(device_id='a', entity_id='light.a'),
            SimpleNamespace(device_id='b', entity_id='light.b'),
            SimpleNamespace(device_id=None, entity_id='light.helper'),
        ]
        devices = {key: SimpleNamespace(id=key) for key in ('a', 'b', 'empty')}
        sources = [SimpleNamespace(
            entry_id=key, title=key, source=key, topic_prefix=key, label='ToIob',
            periodic_interval_minutes=10,
        ) for key in ('one', 'two')]
        seen = []

        def device_payload(hass, source, device, group):
            seen.append((source.entry_id, device.id, [e.entity_id for e in group]))
            return {'name': device.id, 'entity_count': len(group)}

        ns = load_nodes('registry.py', {'integration_payload'}, {
            'dr': SimpleNamespace(async_get=lambda _: SimpleNamespace(devices=devices)),
            'er': SimpleNamespace(async_get=lambda _: SimpleNamespace(entities=entities)),
            'source_configs': lambda _: sources,
            '_matches_source': lambda *args: True,
            '_device_payload': device_payload,
        })
        result = ns['integration_payload'](None)
        entities.values.assert_called_once_with()
        self.assertEqual(seen, [
            ('one', 'a', ['light.a']), ('one', 'b', ['light.b']),
            ('two', 'a', ['light.a']), ('two', 'b', ['light.b']),
        ])
        self.assertEqual([s['entity_count'] for s in result['sources']], [2, 2])
