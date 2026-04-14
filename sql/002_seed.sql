SET NAMES utf8mb4;

INSERT INTO mdm_users (username, display_name, is_admin) VALUES
  ('sales_a', '销售-张三', 0),
  ('marketing_b', '市场-李四', 0),
  ('compliance_c', '合规-王五', 0),
  ('admin', '系统管理员', 1);

INSERT INTO business_object_types (code, name, description) VALUES
  ('CUSTOMER', '客户', 'CRM 客户主数据'),
  ('ORDER', '订单', '销售订单');

INSERT INTO attributes (object_type_id, code, name, data_type, is_sensitive, sort_order) VALUES
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'customer_no', '客户编号', 'string', 0, 10),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'name', '客户名称', 'string', 0, 20),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'phone', '手机号', 'string', 1, 30),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'email', '邮箱', 'string', 1, 40),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'id_card', '证件号', 'string', 1, 50),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'address', '地址', 'string', 0, 60);

INSERT INTO attributes (object_type_id, code, name, data_type, is_sensitive, sort_order) VALUES
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'order_no', '订单号', 'string', 0, 10),
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'amount', '金额', 'decimal', 0, 20),
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'customer_no', '客户编号', 'string', 0, 30),
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'discount', '折扣说明', 'string', 1, 40);

-- 业务实例：两个客户、两个订单
INSERT INTO business_objects (object_type_id, business_key) VALUES
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'C-10001'),
  ((SELECT id FROM business_object_types WHERE code = 'CUSTOMER'), 'C-10002');

INSERT INTO business_objects (object_type_id, business_key) VALUES
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'O-90001'),
  ((SELECT id FROM business_object_types WHERE code = 'ORDER'), 'O-90002');

-- 客户 C-10001 属性值
INSERT INTO attribute_values (object_id, attribute_id, value_text)
SELECT bo.id, a.id, v.val
FROM business_objects bo
JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = 'CUSTOMER'
JOIN attributes a ON a.object_type_id = t.id
JOIN (
  SELECT 'customer_no' AS code, 'C-10001' AS val UNION ALL
  SELECT 'name', '华东科技有限公司' UNION ALL
  SELECT 'phone', '13800001111' UNION ALL
  SELECT 'email', 'contact@east-tech.example' UNION ALL
  SELECT 'id_card', '310101199001011234' UNION ALL
  SELECT 'address', '上海市浦东新区世纪大道100号'
) v ON v.code = a.code
WHERE bo.business_key = 'C-10001';

INSERT INTO attribute_values (object_id, attribute_id, value_text)
SELECT bo.id, a.id, v.val
FROM business_objects bo
JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = 'CUSTOMER'
JOIN attributes a ON a.object_type_id = t.id
JOIN (
  SELECT 'customer_no' AS code, 'C-10002' AS val UNION ALL
  SELECT 'name', '北方贸易行' UNION ALL
  SELECT 'phone', '13900002222' UNION ALL
  SELECT 'email', 'info@north-trade.example' UNION ALL
  SELECT 'id_card', '110101198502021234' UNION ALL
  SELECT 'address', '北京市朝阳区建国路88号'
) v ON v.code = a.code
WHERE bo.business_key = 'C-10002';

INSERT INTO attribute_values (object_id, attribute_id, value_text)
SELECT bo.id, a.id, v.val
FROM business_objects bo
JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = 'ORDER'
JOIN attributes a ON a.object_type_id = t.id
JOIN (
  SELECT 'order_no' AS code, 'O-90001' AS val UNION ALL
  SELECT 'amount', '12800.50' UNION ALL
  SELECT 'customer_no', 'C-10001' UNION ALL
  SELECT 'discount', '大客户年度协议价'
) v ON v.code = a.code
WHERE bo.business_key = 'O-90001';

INSERT INTO attribute_values (object_id, attribute_id, value_text)
SELECT bo.id, a.id, v.val
FROM business_objects bo
JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = 'ORDER'
JOIN attributes a ON a.object_type_id = t.id
JOIN (
  SELECT 'order_no' AS code, 'O-90002' AS val UNION ALL
  SELECT 'amount', '560.00' UNION ALL
  SELECT 'customer_no', 'C-10002' UNION ALL
  SELECT 'discount', '首单促销'
) v ON v.code = a.code
WHERE bo.business_key = 'O-90002';

-- 数据权限：按用户对「可读属性」授权（未授权属性查询结果中不出现）
-- sales_a：可看编号/名称/手机/邮箱（不能看证件号、地址）
INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'sales_a' AND t.code = 'CUSTOMER'
  AND a.code IN ('customer_no', 'name', 'phone', 'email');

INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'sales_a' AND t.code = 'ORDER'
  AND a.code IN ('order_no', 'amount', 'customer_no');

-- marketing_b：客户仅名称+地址；订单仅订单号+客户编号（看不到金额与折扣）
INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'marketing_b' AND t.code = 'CUSTOMER'
  AND a.code IN ('name', 'address');

INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'marketing_b' AND t.code = 'ORDER'
  AND a.code IN ('order_no', 'customer_no');

-- compliance_c：客户与订单全字段可读
INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'compliance_c' AND t.code IN ('CUSTOMER', 'ORDER');

-- admin：全字段可读（用于后台权限管理）
INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'admin' AND t.code IN ('CUSTOMER', 'ORDER');

-- 行级权限（白名单）：若某用户在某对象类型下存在任意行授权，则仅能读这些行；无行授权则不限制行
-- sales_a：仅能看客户 C-10001、订单 O-90001
INSERT INTO user_object_row_grants (user_id, object_id, can_read)
SELECT u.id, bo.id, 1
FROM mdm_users u
JOIN business_objects bo ON 1 = 1
JOIN business_object_types t ON t.id = bo.object_type_id
WHERE u.username = 'sales_a'
  AND ((t.code = 'CUSTOMER' AND bo.business_key = 'C-10001')
    OR (t.code = 'ORDER' AND bo.business_key = 'O-90001'));

-- marketing_b：仅能看客户 C-10002、订单 O-90002
INSERT INTO user_object_row_grants (user_id, object_id, can_read)
SELECT u.id, bo.id, 1
FROM mdm_users u
JOIN business_objects bo ON 1 = 1
JOIN business_object_types t ON t.id = bo.object_type_id
WHERE u.username = 'marketing_b'
  AND ((t.code = 'CUSTOMER' AND bo.business_key = 'C-10002')
    OR (t.code = 'ORDER' AND bo.business_key = 'O-90002'));

-- compliance_c 与 admin：不插入行授权 → 不启用行白名单，可看该类型全部行
