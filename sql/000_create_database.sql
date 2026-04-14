-- 以高权限账号执行一次（例如 root），用于解决 Unknown database 'ai_metadata'
CREATE DATABASE IF NOT EXISTS ai_metadata
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
