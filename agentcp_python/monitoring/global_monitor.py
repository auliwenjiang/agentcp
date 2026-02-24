# -*- coding: utf-8 -*-
"""
全局监控服务单例

提供跨模块访问监控服务的能力，支持AgentID进程和Server进程共享监控数据
"""

_global_monitoring_service = None


def set_global_monitoring_service(monitoring_service):
    """设置全局监控服务实例

    Args:
        monitoring_service: MonitoringService 实例
    """
    global _global_monitoring_service
    _global_monitoring_service = monitoring_service


def get_global_monitoring_service():
    """获取全局监控服务实例

    Returns:
        MonitoringService 实例，如果未设置则返回 None
    """
    return _global_monitoring_service
