import json
import unittest
from pathlib import Path


class ClaudeCutoverTests(unittest.TestCase):
    """Codex was retired on 2026-11-17; the live registry is Anthropic-only."""

    def test_active_registry_is_anthropic_only(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] / 'roles.config.json').read_text())
        models = [x['model'] for x in cfg['roles'].values()] + [x['model'] for x in cfg['agents'].values()]
        models.append(cfg['routing']['postWorkflowAudit']['model'])
        self.assertTrue(all(m['provider'] == 'anthropic' for m in models))
        self.assertEqual(set(cfg['providers']), {'anthropic'})
        self.assertTrue({m['class'] for m in models} <= {'fable', 'opus', 'sonnet', 'haiku'})
        self.assertEqual(cfg['roles']['planner']['model']['class'], 'fable')
        self.assertEqual(cfg['roles']['builder']['model']['class'], 'opus')
