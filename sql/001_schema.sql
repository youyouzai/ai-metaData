-- Metadata + attribute-level read grants (MySQL 8+)
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS attribute_values;
DROP TABLE IF EXISTS user_attribute_grants;
DROP TABLE IF EXISTS user_object_row_grants;
DROP TABLE IF EXISTS attributes;
DROP TABLE IF EXISTS business_objects;
DROP TABLE IF EXISTS business_object_types;
DROP TABLE IF EXISTS mdm_users;

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE mdm_users (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_mdm_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE business_object_types (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description VARCHAR(512) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_bot_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE attributes (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  object_type_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  data_type VARCHAR(32) NOT NULL DEFAULT 'string',
  is_sensitive TINYINT(1) NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_attr_type_code (object_type_id, code),
  CONSTRAINT fk_attr_bot FOREIGN KEY (object_type_id) REFERENCES business_object_types (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_attribute_grants (
  user_id BIGINT UNSIGNED NOT NULL,
  attribute_id BIGINT UNSIGNED NOT NULL,
  can_read TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, attribute_id),
  CONSTRAINT fk_uag_user FOREIGN KEY (user_id) REFERENCES mdm_users (id) ON DELETE CASCADE,
  CONSTRAINT fk_uag_attr FOREIGN KEY (attribute_id) REFERENCES attributes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE business_objects (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  object_type_id BIGINT UNSIGNED NOT NULL,
  business_key VARCHAR(128) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_bo_type_key (object_type_id, business_key),
  CONSTRAINT fk_bo_bot FOREIGN KEY (object_type_id) REFERENCES business_object_types (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_object_row_grants (
  user_id BIGINT UNSIGNED NOT NULL,
  object_id BIGINT UNSIGNED NOT NULL,
  can_read TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, object_id),
  CONSTRAINT fk_uorg_user FOREIGN KEY (user_id) REFERENCES mdm_users (id) ON DELETE CASCADE,
  CONSTRAINT fk_uorg_bo FOREIGN KEY (object_id) REFERENCES business_objects (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE attribute_values (
  object_id BIGINT UNSIGNED NOT NULL,
  attribute_id BIGINT UNSIGNED NOT NULL,
  value_text TEXT NULL,
  PRIMARY KEY (object_id, attribute_id),
  CONSTRAINT fk_av_bo FOREIGN KEY (object_id) REFERENCES business_objects (id) ON DELETE CASCADE,
  CONSTRAINT fk_av_attr FOREIGN KEY (attribute_id) REFERENCES attributes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
