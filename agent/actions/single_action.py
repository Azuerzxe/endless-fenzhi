import json
import os
from maa.custom_action import CustomAction
from maa.context import Context
from maa.agent.agent_server import AgentServer


@AgentServer.custom_action("SingleAction")
class SingleAction(CustomAction):
    COORDS = {}

    @classmethod
    def load_coords(cls, filepath: str):
        """加载坐标映射文件，格式：{"键名": [x, y], ...}"""
        if not os.path.exists(filepath):
            print(f"[SingleAction] 坐标文件不存在: {filepath}")
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, val in data.items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                cls.COORDS[key] = (int(val[0]), int(val[1]))
            elif isinstance(val, dict) and 'x' in val and 'y' in val:
                cls.COORDS[key] = (int(val['x']), int(val['y']))
            else:
                print(f"[SingleAction] 忽略无效坐标项: {key}: {val}")

    def _get_coord(self, key):
        """解析坐标：支持键名、[x,y] 数组、'x,y' 字符串、[x,y,w,h] 区域中心"""
        if key is None:
            print("[SingleAction] 坐标键为空")
            return None
        if isinstance(key, (list, tuple)):
            if len(key) >= 4:  # 区域
                return int(key[0] + key[2] / 2), int(key[1] + key[3] / 2)
            elif len(key) >= 2:
                return int(key[0]), int(key[1])
            else:
                print(f"[SingleAction] 无效的坐标数组: {key}")
                return None
        if isinstance(key, str):
            # 尝试解析 "[x,y]" 或 "[x,y,w,h]"
            if key.startswith('['):
                arr = json.loads(key)
                return self._get_coord(arr)
            # 尝试解析 "x,y"
            if ',' in key:
                parts = key.split(',')
                if len(parts) >= 2:
                    return int(parts[0].strip()), int(parts[1].strip())
            # 从映射表查找
            if key in self.COORDS:
                return self.COORDS[key]
            print(f"[SingleAction] 未定义的坐标键: {key}")
            return None
        print(f"[SingleAction] 无效的坐标类型: {type(key)}")
        return None

    def _get_controller(self, context: Context):
        """兼容不同版本获取控制器"""
        for path in ['tasker.controller', 'controller', '_controller']:
            obj = context
            for part in path.split('.'):
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    obj = None
                    break
            if obj and hasattr(obj, 'post_swipe'):
                return obj
        return None

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param_str = argv.custom_action_param
        if not param_str:
            print("[SingleAction] 参数为空")
            return False

        param_str = param_str.strip()
        if len(param_str) >= 2 and param_str.startswith('"') and param_str.endswith('"'):
            param_str = param_str[1:-1]

        if not param_str:
            print("[SingleAction] 参数为空")
            return False

        controller = self._get_controller(context)
        if controller is None:
            print("[SingleAction] 无法获取控制器")
            return False

        # ----- 处理滑动 S: -----
        if param_str.startswith('S:'):
            parts = param_str[2:].split(',')
            if len(parts) < 2:
                print("[SingleAction] S: 参数不足")
                return False

            from_key = None
            to_key = None
            duration = 100

            # 判断起点是键名还是坐标对
            if parts[0].strip() in self.COORDS:
                from_key = parts[0].strip()
                rest = parts[1:]

                # rest 可能长度为 1（只有终点，无 duration）或 2（终点 + duration）或 3（终点 x,y + duration）
                if len(rest) == 1:
                    # 终点是键名或 x,y 字符串，无 duration
                    to_key = rest[0].strip()
                elif len(rest) == 2:
                    # 终点是键名或 x,y，最后一个是 duration
                    to_key = rest[0].strip()
                    if rest[1].strip().isdigit():
                        duration = int(rest[1].strip())
                    else:
                        print("[SingleAction] 无效的 duration")
                        return False
                elif len(rest) == 3:
                    # 终点是 "x,y" 坐标对，最后一个是 duration
                    to_key = f"{rest[0].strip()},{rest[1].strip()}"
                    if rest[2].strip().isdigit():
                        duration = int(rest[2].strip())
                    else:
                        print("[SingleAction] 无效的 duration")
                        return False
                else:
                    print("[SingleAction] S: 参数格式错误")
                    return False
            else:
                # 起点可能是 "x,y" 坐标对
                if len(parts) >= 4 and parts[1].strip().isdigit():
                    from_key = f"{parts[0].strip()},{parts[1].strip()}"
                    rest = parts[2:]

                    if len(rest) == 1:
                        # 终点是键名，无 duration
                        to_key = rest[0].strip()
                    elif len(rest) == 2:
                        # 终点是键名 + duration
                        to_key = rest[0].strip()
                        if rest[1].strip().isdigit():
                            duration = int(rest[1].strip())
                        else:
                            print("[SingleAction] 无效的 duration")
                            return False
                    elif len(rest) == 3:
                        # 终点是 x,y + duration
                        to_key = f"{rest[0].strip()},{rest[1].strip()}"
                        if rest[2].strip().isdigit():
                            duration = int(rest[2].strip())
                        else:
                            print("[SingleAction] 无效的 duration")
                            return False
                    else:
                        print("[SingleAction] S: 参数格式错误")
                        return False
                else:
                    print("[SingleAction] 无法识别的起点")
                    return False

            coord_from = self._get_coord(from_key)
            if coord_from is None:
                return False
            x1, y1 = coord_from

            coord_to = self._get_coord(to_key) if to_key else None
            if coord_to is None:
                return False
            x2, y2 = coord_to

            controller.post_swipe(x1, y1, x2, y2, duration).wait()
            return True

        # ----- 处理点击 C: -----
        elif param_str.startswith('C:'):
            target_str = param_str[2:].strip()
            coord = self._get_coord(target_str)
            if coord is None:
                return False
            x, y = coord
            controller.post_click(x, y).wait()
            return True

        # ----- JSON 格式 -----
        else:
            if not param_str.startswith('{'):
                print(f"[SingleAction] 无效的参数格式: {param_str[:50]}")
                return False
            params = json.loads(param_str)
            if not isinstance(params, dict):
                print(f"[SingleAction] JSON 参数必须是对象，实际类型: {type(params)}")
                return False

            act_type = params.get('type', '').lower()
            if act_type == 'swipe':
                from_key = params.get('from')
                to_key = params.get('to')
                duration = int(params.get('duration', 100))
                coord_from = self._get_coord(from_key)
                if coord_from is None:
                    return False
                x1, y1 = coord_from
                coord_to = self._get_coord(to_key) if to_key else None
                if coord_to is None:
                    return False
                x2, y2 = coord_to
                controller.post_swipe(x1, y1, x2, y2, duration).wait()
                return True
            elif act_type == 'click':
                target = params.get('target')
                coord = self._get_coord(target)
                if coord is None:
                    return False
                x, y = coord
                controller.post_click(x, y).wait()
                return True
            else:
                print(f"[SingleAction] 未知动作类型: {act_type}")
                return False