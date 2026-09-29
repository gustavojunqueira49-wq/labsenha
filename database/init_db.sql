-- Executar como superusuário do PostgreSQL (ex.: psql -U postgres -f init_db.sql)
-- TROQUE A SENHA antes de executar e use a mesma no arquivo .env (DATABASE_URL).
CREATE ROLE senhas WITH LOGIN PASSWORD 'TROQUE_ESTA_SENHA';
CREATE DATABASE senhas_lab OWNER senhas ENCODING 'UTF8';
