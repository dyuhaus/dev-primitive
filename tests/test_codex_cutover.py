import json
import unittest
from pathlib import Path


class CodexCutoverTests(unittest.TestCase):
    def test_active_registry_is_openai_xhigh_only(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] / 'roles.config.json').read_text())
        models = [x['model'] for x in cfg['roles'].values()] + [x['model'] for x in cfg['agents'].values()]
        models.append(cfg['routing']['postWorkflowAudit']['model'])
        self.assertTrue(all(m['provider'] == 'openai' and m['effort'] == 'xhigh' for m in models))
        self.assertEqual({m['class'] for m in models}, {'gpt-5.6-sol', 'gpt-5.6-terra'})
