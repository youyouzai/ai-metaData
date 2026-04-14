-- 在已有库上增量升级（若已执行过新版 001/002 则无需运行）
SET NAMES utf8mb4;

ALTER TABLE mdm_users
  ADD COLUMN is_admin TINYINT(1) NOT NULL DEFAULT 0 AFTER display_name;

CREATE TABLE IF NOT EXISTS user_object_row_grants (
  user_id BIGINT UNSIGNED NOT NULL,
  object_id BIGINT UNSIGNED NOT NULL,
  can_read TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, object_id),
  CONSTRAINT fk_uorg_user FOREIGN KEY (user_id) REFERENCES mdm_users (id) ON DELETE CASCADE,
  CONSTRAINT fk_uorg_bo FOREIGN KEY (object_id) REFERENCES business_objects (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO mdm_users (username, display_name, is_admin)
SELECT 'admin', '系统管理员', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM mdm_users WHERE username = 'admin');

INSERT INTO user_attribute_grants (user_id, attribute_id, can_read)
SELECT u.id, a.id, 1
FROM mdm_users u
CROSS JOIN attributes a
JOIN business_object_types t ON t.id = a.object_type_id
WHERE u.username = 'admin' AND t.code IN ('CUSTOMER', 'ORDER')
  AND NOT EXISTS (
    SELECT 1 FROM user_attribute_grants g
    WHERE g.user_id = u.id AND g.attribute_id = a.id
  );

INSERT INTO user_object_row_grants (user_id, object_id, can_read)
SELECT u.id, bo.id, 1
FROM mdm_users u
JOIN business_objects bo ON 1 = 1
JOIN business_object_types t ON t.id = bo.object_type_id
WHERE u.username = 'sales_a'
  AND ((t.code = 'CUSTOMER' AND bo.business_key = 'C-10001')
    OR (t.code = 'ORDER' AND bo.business_key = 'O-90001'))
  AND NOT EXISTS (
    SELECT 1 FROM user_object_row_grants g WHERE g.user_id = u.id AND g.object_id = bo.id
  );

INSERT INTO user_object_row_grants (user_id, object_id, can_read)
SELECT u.id, bo.id, 1
FROM mdm_users u
JOIN business_objects bo ON 1 = 1
JOIN business_object_types t ON t.id = bo.object_type_id
WHERE u.username = 'marketing_b'
  AND ((t.code = 'CUSTOMER' AND bo.business_key = 'C-10002')
    OR (t.code = 'ORDER' AND bo.business_key = 'O-90002'))
  AND NOT EXISTS (
    SELECT 1 FROM user_object_row_grants g WHERE g.user_id = u.id AND g.object_id = bo.id
  );

UPDATE mdm_users SET is_admin = 1 WHERE username = 'admin';
