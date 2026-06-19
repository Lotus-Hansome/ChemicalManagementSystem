import csv
import tempfile
import unittest
from pathlib import Path

from app.auth import authenticate, create_user, has_permission, list_users, require_permission, set_role_permission
from app.data_store import DataStore
from app.exceptions import AppError, PermissionDeniedError
from app.report_service import ReportService

class CoreLogicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp_dir.name) / "cms_data.db"
        self.store = DataStore(self.data_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_auth_permissions(self) -> None:
        admin = authenticate("admin", "admin123", self.data_path)
        operator = authenticate("operator", "operator123", self.data_path)
        self.assertTrue(has_permission(admin, "report_export", self.data_path))
        self.assertFalse(has_permission(operator, "report_export", self.data_path))
        require_permission(admin, "chemical_manage", self.data_path)
        with self.assertRaises(PermissionDeniedError):
            require_permission(operator, "chemical_manage", self.data_path)

    def test_user_and_role_permissions_are_table_driven(self) -> None:
        create_user("safety", "safety123", "安全员", "operator", self.data_path)
        users = {user["username"]: user for user in list_users(self.data_path)}
        self.assertEqual(users["safety"]["role_code"], "operator")
        safety = authenticate("safety", "safety123", self.data_path)
        self.assertFalse(has_permission(safety, "report_export", self.data_path))
        set_role_permission("operator", "report_export", True, self.data_path)
        self.assertTrue(has_permission(safety, "report_export", self.data_path))
        set_role_permission("operator", "report_export", False, self.data_path)

    def test_search_and_inventory_adjust(self) -> None:
        rows = self.store.search_chemicals(keyword="甲醇")
        self.assertEqual(rows[0]["id"], "C001")
        updated = self.store.adjust_inventory("C001", 10)
        self.assertEqual(updated["inventory"], 1210.0)
        with self.assertRaises(AppError):
            self.store.adjust_inventory("C001", -99999)

    def test_parameter_alarm_acknowledge(self) -> None:
        alarm = next(item for item in self.store.get_parameters() if item["status"] == "报警")
        updated = self.store.acknowledge_alarm(alarm["id"], "tester")
        self.assertTrue(updated["acknowledged"])

    def test_parameter_sampling_creates_trend_and_alarm_history(self) -> None:
        before_samples = len(self.store.get_parameter_samples("P001", limit=100))
        self.store.simulate_parameter_sampling()
        after_samples = len(self.store.get_parameter_samples("P001", limit=100))
        self.assertGreater(after_samples, before_samples)
        self.store.update_parameter_threshold("P001", 0, 1)
        self.assertTrue(self.store.get_alarm_history(limit=10))

    def test_audit_log_records_key_action(self) -> None:
        self.store.log_action("系统管理员", "管理员", "测试操作", "C001", "单元测试")
        self.store.log_action("现场操作员", "普通操作员", "新建工单", "WO001", "单元测试")
        logs = self.store.get_audit_logs()
        self.assertEqual(logs[0]["username"], "现场操作员")
        self.assertEqual(logs[0]["action"], "新建工单")
        self.assertEqual(logs[1]["target"], "C001")

    def test_work_order_flow_and_report_export(self) -> None:
        created = self.store.add_work_order(
            {
                "title": "测试工单",
                "area": "A车间",
                "priority": "中",
                "status": "待处理",
                "due_date": "2026-06-30",
                "description": "测试描述",
            },
            owner="tester",
        )
        advanced = self.store.advance_work_order(created["id"], allow_close=False)
        self.assertEqual(advanced["status"], "处理中")

        report_dir = Path(self.temp_dir.name) / "reports"
        path = ReportService(self.store, report_dir).export("summary")
        self.assertTrue(path.exists())
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file))
        self.assertEqual(rows[0], ["模块", "指标", "数值"])

if __name__ == "__main__":
    unittest.main()