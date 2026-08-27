# actions/batch_swipe.py
import json
import time
import os
from maa.custom_action import CustomAction
from maa.context import Context


class BatchSwipe(CustomAction):
    """
    批量执行滑动/点击/等待操作，零识别开销。
    坐标使用键名引用，需提前通过 load_coords() 加载坐标映射表。
    参数格式（JSON 数组）：
    [
        {"type": "swipe", "from": "种植物_初始化_第二个槽位", "to": "种植物_初始化_第二个槽位", "duration": 100},
        {"type": "click", "key": "种植物_初始化_铲子位置"},
        {"type": "sleep", "time": 0.2}
    ]
    若 "to" 省略，表示原地滑动（相当于点击）。
    """
    # 坐标映射表：键名 -> (x, y)
    COORDS = {}

    @classmethod
    def load_coords(cls, filepath: str):
        """从 JSON 文件加载坐标映射。文件格式：{"键名": [x, y], ...}"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"坐标文件不存在: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 兼容 {"键名": [x, y]} 和 {"键名": {"x": x, "y": y}}
        for key, val in data.items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                cls.COORDS[key] = (int(val[0]), int(val[1]))
            elif isinstance(val, dict) and 'x' in val and 'y' in val:
                cls.COORDS[key] = (int(val['x']), int(val['y']))
            else:
                print(f"[BatchSwipe] 忽略无效坐标项: {key}: {val}")

    def _get_coord(self, key):
        """根据键名获取坐标，支持直接传入 [x, y] 列表"""
        if key is None:
            raise KeyError("坐标键不能为空")
        if isinstance(key, (list, tuple)) and len(key) >= 2:
            return int(key[0]), int(key[1])
        if isinstance(key, str):
            if key in self.COORDS:
                return self.COORDS[key]
            else:
                raise KeyError(f"未定义的坐标键: {key}")
        raise KeyError(f"无效的坐标键: {key}")

    def _get_controller(self, context: Context):
        """兼容不同版本获取控制器"""
        # 尝试多种常见路径
        for path in ['tasker.controller', 'controller', '_controller']:
            try:
                obj = context
                for part in path.split('.'):
                    obj = getattr(obj, part)
                if obj and hasattr(obj, 'post_swipe'):
                    return obj
            except:
                continue
        return None

    def run(self, context: Context, argv: str) -> bool:
        try:
            actions = json.loads(argv)
            if not isinstance(actions, list):
                raise ValueError("参数必须是 JSON 数组")
        except Exception as e:
            context.logger.error(f"BatchSwipe: 参数解析失败: {e}")
            return False

        controller = self._get_controller(context)
        if controller is None:
            context.logger.error("BatchSwipe: 无法获取控制器")
            return False

        for act in actions:
            try:
                act_type = act.get('type', '').lower()
                if act_type == 'swipe':
                    from_key = act.get('from', act.get('begin'))
                    to_key = act.get('to', act.get('end'))
                    x1, y1 = self._get_coord(from_key)
                    if to_key:
                        x2, y2 = self._get_coord(to_key)
                    else:
                        x2, y2 = x1, y1   # 原地滑动
                    duration = int(act.get('duration', 500))
                    controller.post_swipe(x1, y1, x2, y2, duration).wait()
                elif act_type == 'click':
                    key = act.get('key', act.get('name'))
                    x, y = self._get_coord(key)
                    controller.post_click(x, y).wait()
                elif act_type == 'sleep':
                    time.sleep(float(act.get('time', 0.2)))
                else:
                    context.logger.warning(f"BatchSwipe: 未知动作类型 '{act_type}'，已跳过")
            except KeyError as e:
                context.logger.error(f"BatchSwipe: 缺少坐标键 {e}")
                return False
            except Exception as e:
                context.logger.error(f"BatchSwipe: 动作执行失败: {e}")
                return False
        return True