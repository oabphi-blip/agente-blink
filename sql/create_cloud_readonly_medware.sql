-- ============================================================
-- Setup Firebird para conexão read-only Cloud (Lovable Fase 2)
-- Executar no CLINICAS.FDB de produção (E:\Medware Clinicas\BD\CLINICAS.FDB)
-- Requer conexão como SYSDBA.
--
-- Fábio Blink Oftalmologia - 03/07/2026
-- Cria:
--   1 usuário read-only: CLOUD_READONLY
--   3 views:             VW_CLOUD_AGENDAMENTOS, VW_CLOUD_MEDICOS, VW_CLOUD_UNIDADES
--
-- ZERO permissão de escrita. Objeto totalmente reversível com:
--   DROP VIEW VW_CLOUD_AGENDAMENTOS;
--   DROP VIEW VW_CLOUD_MEDICOS;
--   DROP VIEW VW_CLOUD_UNIDADES;
--   DROP USER CLOUD_READONLY;
-- ============================================================

-- 1. Cria usuário read-only
-- SUBSTITUA <SENHA_FORTE> por senha gerada com pwgen -s 32 1 ou similar
CREATE USER CLOUD_READONLY PASSWORD '<SENHA_FORTE_GERAR_AQUI>';

-- 2. Views expostas ao Cloud (só campos essenciais)
CREATE VIEW VW_CLOUD_AGENDAMENTOS AS
SELECT
    A.CODAGENDAMENTO,
    A.CODMEDICO,
    A.CODUNIDADE,
    A.DATA,
    A.HORA,
    A.DURACAO_MIN,
    A.STATUS,
    A.CODPACIENTE
FROM AGENDAMENTO A;

CREATE VIEW VW_CLOUD_MEDICOS AS
SELECT
    CODMEDICO,
    NOME,
    ESPECIALIDADE
FROM MEDICO;

CREATE VIEW VW_CLOUD_UNIDADES AS
SELECT
    CODUNIDADE,
    NOME
FROM UNIDADE;

-- 3. Grants apenas SELECT nas views
GRANT SELECT ON VW_CLOUD_AGENDAMENTOS TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_MEDICOS       TO CLOUD_READONLY;
GRANT SELECT ON VW_CLOUD_UNIDADES      TO CLOUD_READONLY;

-- 4. Confirma (deve retornar 3 linhas)
SELECT RDB$USER, RDB$RELATION_NAME, RDB$PRIVILEGE
FROM RDB$USER_PRIVILEGES
WHERE RDB$USER = 'CLOUD_READONLY';

COMMIT;

-- ============================================================
-- ROLLBACK COMPLETO (se der problema):
-- ============================================================
-- REVOKE SELECT ON VW_CLOUD_AGENDAMENTOS FROM CLOUD_READONLY;
-- REVOKE SELECT ON VW_CLOUD_MEDICOS       FROM CLOUD_READONLY;
-- REVOKE SELECT ON VW_CLOUD_UNIDADES      FROM CLOUD_READONLY;
-- DROP VIEW VW_CLOUD_AGENDAMENTOS;
-- DROP VIEW VW_CLOUD_MEDICOS;
-- DROP VIEW VW_CLOUD_UNIDADES;
-- DROP USER CLOUD_READONLY;
-- COMMIT;
