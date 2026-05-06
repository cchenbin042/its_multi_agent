import re
import json
from pathlib import Path


class BrandAnonymizer:
    def __init__(self, map_file: str = None):
        self.default_rules = {
            "联想": "设备厂商",
            "Lenovo": "品牌方",
            "联想电脑管家": "系统管理软件",
            "联想笔记本": "笔记本电脑",
            "联想手机": "手机",
        }
        self.rules = dict(self.default_rules)
        if map_file:
            self._load_rules(map_file)

    def _load_rules(self, map_file: str):
        path = Path(map_file)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                custom = json.load(f)
                self.rules.update(custom)

    def anonymize(self, text: str) -> str:
        sorted_keys = sorted(self.rules.keys(), key=len, reverse=True)
        for key in sorted_keys:
            text = text.replace(key, self.rules[key])
        return text
