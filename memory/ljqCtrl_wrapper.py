"""
ljqCtrl_wrapper.py - ljqCtrl高层封装，消除坐标/DPI陷阱
自动处理：窗口激活、物理/逻辑坐标转换、客户区偏移、文本输入

用法：
    from ljqCtrl_wrapper import EasyCtrl
    
    ctrl = EasyCtrl("窗口标题")
    ctrl.click(100, 200)  # 点击窗口客户区(100,200)
    ctrl.type_text("Hello")  # 输入文本
    ctrl.find_and_click("button.png")  # 找图点击
"""

import sys
import os
import time
import pygetwindow as gw
import pyperclip
import win32gui
import win32con

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ljqCtrl


class EasyCtrl:
    """ljqCtrl高层封装，自动处理DPI和窗口坐标"""
    
    def __init__(self, window_title=None):
        """
        初始化控制器
        Args:
            window_title: 窗口标题(支持模糊匹配)，None表示全屏操作
        """
        self.window_title = window_title
        self._hwnd = None
        self._client_offset = (0, 0)  # 客户区原点在屏幕上的物理坐标
        
    def _activate(self):
        """激活目标窗口"""
        if not self.window_title:
            return
        wins = gw.getWindowsWithTitle(self.window_title)
        if not wins:
            raise RuntimeError(f"未找到窗口: {self.window_title}")
        win = wins[0]
        win.restore()
        win.activate()
        time.sleep(0.3)
        
        # 获取客户区偏移
        self._hwnd = win32gui.FindWindow(None, win.title)
        if self._hwnd:
            # ClientToScreen获取客户区原点(逻辑坐标)
            client_origin = win32gui.ClientToScreen(self._hwnd, (0, 0))
            # 转换为物理坐标
            self._client_offset = (
                int(client_origin[0] / ljqCtrl.dpi_scale),
                int(client_origin[1] / ljqCtrl.dpi_scale)
            )
    
    def client_to_physical(self, client_x, client_y):
        """
        将客户区坐标转换为屏幕物理坐标
        Args:
            client_x, client_y: 客户区坐标(逻辑像素，即截图坐标)
        Returns:
            (phys_x, phys_y): 屏幕物理坐标
        """
        # 客户区坐标先转物理
        phys_x = int(client_x / ljqCtrl.dpi_scale)
        phys_y = int(client_y / ljqCtrl.dpi_scale)
        # 加上客户区原点偏移
        return (phys_x + self._client_offset[0], phys_y + self._client_offset[1])
    
    def click(self, client_x, client_y, activate=True):
        """
        点击窗口客户区指定位置
        Args:
            client_x, client_y: 客户区坐标(截图坐标系)
            activate: 是否先激活窗口
        """
        if activate:
            self._activate()
        phys_x, phys_y = self.client_to_physical(client_x, client_y)
        ljqCtrl.Click(phys_x, phys_y)
        
    def double_click(self, client_x, client_y, activate=True):
        """双击窗口客户区指定位置"""
        if activate:
            self._activate()
        phys_x, phys_y = self.client_to_physical(client_x, client_y)
        ljqCtrl.SetCursorPos((phys_x, phys_y))
        ljqCtrl.MouseDClick()
    
    def type_text(self, text, triple_click_to_clear=True):
        """
        向当前焦点输入框输入文本
        Args:
            text: 要输入的文本
            triple_click_to_clear: 是否三击选中清除(用于输入框)
        """
        if triple_click_to_clear:
            time.sleep(0.1)
            ljqCtrl.MouseDClick()  # 双击选中
            time.sleep(0.1)
        pyperclip.copy(text)
        ljqCtrl.Press('ctrl+v')
        
    def find_and_click(self, image_path, threshold=0.8, activate=True):
        """
        找图并点击
        Args:
            image_path: 模板图片路径
            threshold: 匹配阈值
            activate: 是否先激活窗口
        Returns:
            (found, position): 是否找到，点击位置(客户区坐标)
        """
        if activate:
            self._activate()
        
        # 获取窗口截图区域
        if self._hwnd:
            rect = win32gui.GetWindowRect(self._hwnd)
            # 转物理坐标
            wrect = [int(v / ljqCtrl.dpi_scale) for v in rect]
        else:
            wrect = None
            
        pos, found = ljqCtrl.FindBlock(image_path, wrect=wrect, threshold=threshold)
        
        if found:
            # 转换为客户区坐标
            client_x = int((pos[0] - self._client_offset[0]) * ljqCtrl.dpi_scale)
            client_y = int((pos[1] - self._client_offset[1]) * ljqCtrl.dpi_scale)
            self.click(client_x, client_y, activate=False)
            return True, (client_x, client_y)
        return False, None
    
    def press(self, keys):
        """
        发送快捷键
        Args:
            keys: 快捷键字符串，如 'ctrl+c', 'alt+f4'
        """
        ljqCtrl.Press(keys)
    
    def move_to(self, client_x, client_y, activate=True):
        """移动鼠标到指定位置"""
        if activate:
            self._activate()
        phys_x, phys_y = self.client_to_physical(client_x, client_y)
        ljqCtrl.SetCursorPos((phys_x, phys_y))
    
    @staticmethod
    def screenshot_window(window_title):
        """
        截取指定窗口
        Returns:
            PIL.Image: 截图图像
        """
        wins = gw.getWindowsWithTitle(window_title)
        if not wins:
            raise RuntimeError(f"未找到窗口: {window_title}")
        hwnd = win32gui.FindWindow(None, wins[0].title)
        return ljqCtrl.GrabWindow(hwnd)


# 便捷函数(无需实例化)
def click_window(title, x, y):
    """点击指定窗口的客户区坐标"""
    ctrl = EasyCtrl(title)
    ctrl.click(x, y)

def type_text(text):
    """输入文本(通过剪贴板)"""
    pyperclip.copy(text)
    ljqCtrl.Press('ctrl+v')

def find_and_click(image_path, title=None, threshold=0.8):
    """找图并点击"""
    ctrl = EasyCtrl(title)
    return ctrl.find_and_click(image_path, threshold=threshold)


if __name__ == '__main__':
    print("EasyCtrl测试")
    print(f"dpi_scale: {ljqCtrl.dpi_scale}")
    print("封装API: EasyCtrl类 / click_window / type_text / find_and_click")
