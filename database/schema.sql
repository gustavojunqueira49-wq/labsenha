-- Esquema do banco (PostgreSQL 16) — gerado a partir das migrações (backend/migrations).
-- Referência para DBAs. Para instalar/atualizar use: python -m app.cli migrate
-- Tabelas: users, roles, permissions (+ role_permissions), sessions, tickets, ticket_types, priorities,
--   queue_events, ticket_sequences (numeração atômica), counters (guichês), attendants, printers,
--   print_jobs, print_agents, panels, computers, settings, audit_logs, backups.
\restrict uGEgS6lMmUFugri2RNvApnRJASKpbYXrNivmncPgyn0wrkErfU803opxNggxE9R
CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);
CREATE TABLE public.attendants (
    id integer NOT NULL,
    user_id integer NOT NULL,
    counter_id integer,
    counter_since timestamp with time zone,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.attendants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.attendants_id_seq OWNED BY public.attendants.id;
CREATE TABLE public.audit_logs (
    id bigint NOT NULL,
    created_at timestamp with time zone NOT NULL,
    user_id integer,
    username character varying(50),
    action character varying(60) NOT NULL,
    entity character varying(40),
    entity_id character varying(40),
    details json,
    ip_address character varying(64)
);
CREATE SEQUENCE public.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;
CREATE TABLE public.backups (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    path character varying(1000) NOT NULL,
    size_bytes bigint NOT NULL,
    kind character varying(15) NOT NULL,
    status character varying(10) NOT NULL,
    error text,
    created_at timestamp with time zone NOT NULL,
    created_by integer,
    restored_at timestamp with time zone
);
CREATE SEQUENCE public.backups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.backups_id_seq OWNED BY public.backups.id;
CREATE TABLE public.computers (
    id integer NOT NULL,
    name character varying(80) NOT NULL,
    ip_address character varying(64),
    description character varying(255) NOT NULL,
    active boolean NOT NULL,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.computers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.computers_id_seq OWNED BY public.computers.id;
CREATE TABLE public.counters (
    id integer NOT NULL,
    code character varying(20) NOT NULL,
    name character varying(60) NOT NULL,
    spoken_name character varying(80) NOT NULL,
    "position" integer NOT NULL,
    active boolean NOT NULL,
    accepted_type_ids json,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.counters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.counters_id_seq OWNED BY public.counters.id;
CREATE TABLE public.panels (
    id integer NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(80) NOT NULL,
    computer_id integer,
    history_size integer NOT NULL,
    active boolean NOT NULL,
    last_seen_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.panels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.panels_id_seq OWNED BY public.panels.id;
CREATE TABLE public.permissions (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    description character varying(255) NOT NULL
);
CREATE SEQUENCE public.permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.permissions_id_seq OWNED BY public.permissions.id;
CREATE TABLE public.print_agents (
    id integer NOT NULL,
    name character varying(80) NOT NULL,
    token_hash character varying(64) NOT NULL,
    computer_id integer,
    active boolean NOT NULL,
    last_seen_at timestamp with time zone,
    version character varying(30),
    hostname character varying(120),
    last_error character varying(500),
    was_online boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.print_agents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.print_agents_id_seq OWNED BY public.print_agents.id;
CREATE TABLE public.print_jobs (
    id bigint NOT NULL,
    ticket_id bigint,
    printer_id integer,
    kind character varying(10) NOT NULL,
    status character varying(10) NOT NULL,
    attempts integer NOT NULL,
    last_error character varying(500),
    payload json,
    created_at timestamp with time zone NOT NULL,
    created_by integer,
    claimed_at timestamp with time zone,
    printed_at timestamp with time zone,
    next_attempt_at timestamp with time zone,
    CONSTRAINT ck_print_status CHECK (((status)::text = ANY ((ARRAY['PENDENTE'::character varying, 'ENVIANDO'::character varying, 'IMPRESSO'::character varying, 'ERRO'::character varying, 'CANCELADO'::character varying])::text[])))
);
CREATE SEQUENCE public.print_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.print_jobs_id_seq OWNED BY public.print_jobs.id;
CREATE TABLE public.printers (
    id integer NOT NULL,
    name character varying(80) NOT NULL,
    connection character varying(10) NOT NULL,
    agent_id integer,
    system_name character varying(120) NOT NULL,
    host character varying(120),
    port integer NOT NULL,
    paper_width_mm integer NOT NULL,
    chars_per_line integer NOT NULL,
    margin_top integer NOT NULL,
    margin_bottom integer NOT NULL,
    code_size integer NOT NULL,
    cut boolean NOT NULL,
    encoding character varying(20) NOT NULL,
    is_default boolean NOT NULL,
    active boolean NOT NULL,
    status character varying(20) NOT NULL,
    status_detail character varying(500),
    status_at timestamp with time zone,
    last_print_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_printer_connection CHECK (((connection)::text = ANY ((ARRAY['AGENT'::character varying, 'NETWORK'::character varying])::text[])))
);
CREATE SEQUENCE public.printers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.printers_id_seq OWNED BY public.printers.id;
CREATE TABLE public.priorities (
    id integer NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(80) NOT NULL,
    description character varying(500) NOT NULL,
    legal_basis character varying(500) NOT NULL,
    rank integer NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.priorities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.priorities_id_seq OWNED BY public.priorities.id;
CREATE TABLE public.queue_events (
    id bigint NOT NULL,
    ticket_id bigint NOT NULL,
    event_type character varying(30) NOT NULL,
    from_status character varying(20),
    to_status character varying(20),
    user_id integer,
    counter_id integer,
    created_at timestamp with time zone NOT NULL,
    details json
);
CREATE SEQUENCE public.queue_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.queue_events_id_seq OWNED BY public.queue_events.id;
CREATE TABLE public.role_permissions (
    role_id integer NOT NULL,
    permission_id integer NOT NULL
);
CREATE TABLE public.roles (
    id integer NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(80) NOT NULL,
    description character varying(255) NOT NULL,
    is_system boolean NOT NULL
);
CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;
CREATE TABLE public.sessions (
    id bigint NOT NULL,
    token_hash character varying(64) NOT NULL,
    user_id integer NOT NULL,
    computer_id integer,
    ip_address character varying(64),
    user_agent character varying(255),
    created_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone
);
CREATE SEQUENCE public.sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.sessions_id_seq OWNED BY public.sessions.id;
CREATE TABLE public.settings (
    key character varying(80) NOT NULL,
    value json NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    updated_by integer
);
CREATE TABLE public.ticket_sequences (
    id integer NOT NULL,
    ticket_type_id integer NOT NULL,
    seq_date date NOT NULL,
    last_number integer NOT NULL
);
CREATE SEQUENCE public.ticket_sequences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.ticket_sequences_id_seq OWNED BY public.ticket_sequences.id;
CREATE TABLE public.ticket_types (
    id integer NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(80) NOT NULL,
    prefix character varying(4) NOT NULL,
    color character varying(9) NOT NULL,
    "position" integer NOT NULL,
    priority_level integer NOT NULL,
    requires_category boolean NOT NULL,
    description character varying(255) NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.ticket_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.ticket_types_id_seq OWNED BY public.ticket_types.id;
CREATE TABLE public.tickets (
    id bigint NOT NULL,
    code character varying(20) NOT NULL,
    number integer NOT NULL,
    ticket_type_id integer NOT NULL,
    priority_id integer,
    status character varying(20) NOT NULL,
    service_date date NOT NULL,
    seq_date date NOT NULL,
    created_at timestamp with time zone NOT NULL,
    created_by integer,
    computer_id integer,
    called_at timestamp with time zone,
    last_called_at timestamp with time zone,
    recall_count integer NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    counter_id integer,
    attendant_id integer,
    status_reason character varying(255),
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_ticket_status CHECK (((status)::text = ANY ((ARRAY['AGUARDANDO'::character varying, 'CHAMADA'::character varying, 'RECHAMADA'::character varying, 'EM_ATENDIMENTO'::character varying, 'ATENDIDA'::character varying, 'NAO_COMPARECEU'::character varying, 'CANCELADA'::character varying])::text[])))
);
CREATE SEQUENCE public.tickets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.tickets_id_seq OWNED BY public.tickets.id;
CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    full_name character varying(120) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role_id integer NOT NULL,
    active boolean NOT NULL,
    must_change_password boolean NOT NULL,
    failed_attempts integer NOT NULL,
    locked_until timestamp with time zone,
    last_login_at timestamp with time zone,
    password_changed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;
ALTER TABLE ONLY public.attendants ALTER COLUMN id SET DEFAULT nextval('public.attendants_id_seq'::regclass);
ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);
ALTER TABLE ONLY public.backups ALTER COLUMN id SET DEFAULT nextval('public.backups_id_seq'::regclass);
ALTER TABLE ONLY public.computers ALTER COLUMN id SET DEFAULT nextval('public.computers_id_seq'::regclass);
ALTER TABLE ONLY public.counters ALTER COLUMN id SET DEFAULT nextval('public.counters_id_seq'::regclass);
ALTER TABLE ONLY public.panels ALTER COLUMN id SET DEFAULT nextval('public.panels_id_seq'::regclass);
ALTER TABLE ONLY public.permissions ALTER COLUMN id SET DEFAULT nextval('public.permissions_id_seq'::regclass);
ALTER TABLE ONLY public.print_agents ALTER COLUMN id SET DEFAULT nextval('public.print_agents_id_seq'::regclass);
ALTER TABLE ONLY public.print_jobs ALTER COLUMN id SET DEFAULT nextval('public.print_jobs_id_seq'::regclass);
ALTER TABLE ONLY public.printers ALTER COLUMN id SET DEFAULT nextval('public.printers_id_seq'::regclass);
ALTER TABLE ONLY public.priorities ALTER COLUMN id SET DEFAULT nextval('public.priorities_id_seq'::regclass);
ALTER TABLE ONLY public.queue_events ALTER COLUMN id SET DEFAULT nextval('public.queue_events_id_seq'::regclass);
ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);
ALTER TABLE ONLY public.sessions ALTER COLUMN id SET DEFAULT nextval('public.sessions_id_seq'::regclass);
ALTER TABLE ONLY public.ticket_sequences ALTER COLUMN id SET DEFAULT nextval('public.ticket_sequences_id_seq'::regclass);
ALTER TABLE ONLY public.ticket_types ALTER COLUMN id SET DEFAULT nextval('public.ticket_types_id_seq'::regclass);
ALTER TABLE ONLY public.tickets ALTER COLUMN id SET DEFAULT nextval('public.tickets_id_seq'::regclass);
ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);
ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
ALTER TABLE ONLY public.attendants
    ADD CONSTRAINT attendants_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.attendants
    ADD CONSTRAINT attendants_user_id_key UNIQUE (user_id);
ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.backups
    ADD CONSTRAINT backups_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.computers
    ADD CONSTRAINT computers_name_key UNIQUE (name);
ALTER TABLE ONLY public.computers
    ADD CONSTRAINT computers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.counters
    ADD CONSTRAINT counters_code_key UNIQUE (code);
ALTER TABLE ONLY public.counters
    ADD CONSTRAINT counters_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.panels
    ADD CONSTRAINT panels_code_key UNIQUE (code);
ALTER TABLE ONLY public.panels
    ADD CONSTRAINT panels_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_code_key UNIQUE (code);
ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.print_agents
    ADD CONSTRAINT print_agents_name_key UNIQUE (name);
ALTER TABLE ONLY public.print_agents
    ADD CONSTRAINT print_agents_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.print_agents
    ADD CONSTRAINT print_agents_token_hash_key UNIQUE (token_hash);
ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.printers
    ADD CONSTRAINT printers_name_key UNIQUE (name);
ALTER TABLE ONLY public.printers
    ADD CONSTRAINT printers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.priorities
    ADD CONSTRAINT priorities_code_key UNIQUE (code);
ALTER TABLE ONLY public.priorities
    ADD CONSTRAINT priorities_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.queue_events
    ADD CONSTRAINT queue_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);
ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_code_key UNIQUE (code);
ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_token_hash_key UNIQUE (token_hash);
ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (key);
ALTER TABLE ONLY public.ticket_sequences
    ADD CONSTRAINT ticket_sequences_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.ticket_types
    ADD CONSTRAINT ticket_types_code_key UNIQUE (code);
ALTER TABLE ONLY public.ticket_types
    ADD CONSTRAINT ticket_types_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.ticket_types
    ADD CONSTRAINT ticket_types_prefix_key UNIQUE (prefix);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.ticket_sequences
    ADD CONSTRAINT uq_sequence_type_date UNIQUE (ticket_type_id, seq_date);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT uq_ticket_number UNIQUE (ticket_type_id, seq_date, number);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);
CREATE INDEX ix_attendants_counter_id ON public.attendants USING btree (counter_id);
CREATE INDEX ix_audit_at ON public.audit_logs USING btree (created_at);
CREATE INDEX ix_print_jobs_queue ON public.print_jobs USING btree (status, printer_id, id);
CREATE INDEX ix_print_jobs_ticket_id ON public.print_jobs USING btree (ticket_id);
CREATE INDEX ix_queue_events_ticket ON public.queue_events USING btree (ticket_id, created_at);
CREATE INDEX ix_sessions_user_id ON public.sessions USING btree (user_id);
CREATE INDEX ix_tickets_attendant_id ON public.tickets USING btree (attendant_id);
CREATE INDEX ix_tickets_code_date ON public.tickets USING btree (service_date, code);
CREATE INDEX ix_tickets_counter_id ON public.tickets USING btree (counter_id);
CREATE INDEX ix_tickets_queue ON public.tickets USING btree (status, service_date, created_at);
CREATE INDEX ix_tickets_service_date ON public.tickets USING btree (service_date);
CREATE INDEX ix_tickets_ticket_type_id ON public.tickets USING btree (ticket_type_id);
CREATE INDEX ix_users_role_id ON public.users USING btree (role_id);
ALTER TABLE ONLY public.attendants
    ADD CONSTRAINT attendants_counter_id_fkey FOREIGN KEY (counter_id) REFERENCES public.counters(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.attendants
    ADD CONSTRAINT attendants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.backups
    ADD CONSTRAINT backups_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.panels
    ADD CONSTRAINT panels_computer_id_fkey FOREIGN KEY (computer_id) REFERENCES public.computers(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.print_agents
    ADD CONSTRAINT print_agents_computer_id_fkey FOREIGN KEY (computer_id) REFERENCES public.computers(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);
ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_printer_id_fkey FOREIGN KEY (printer_id) REFERENCES public.printers(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);
ALTER TABLE ONLY public.printers
    ADD CONSTRAINT printers_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.print_agents(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.queue_events
    ADD CONSTRAINT queue_events_counter_id_fkey FOREIGN KEY (counter_id) REFERENCES public.counters(id);
ALTER TABLE ONLY public.queue_events
    ADD CONSTRAINT queue_events_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);
ALTER TABLE ONLY public.queue_events
    ADD CONSTRAINT queue_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);
ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_computer_id_fkey FOREIGN KEY (computer_id) REFERENCES public.computers(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.ticket_sequences
    ADD CONSTRAINT ticket_sequences_ticket_type_id_fkey FOREIGN KEY (ticket_type_id) REFERENCES public.ticket_types(id);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_attendant_id_fkey FOREIGN KEY (attendant_id) REFERENCES public.users(id);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_computer_id_fkey FOREIGN KEY (computer_id) REFERENCES public.computers(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_counter_id_fkey FOREIGN KEY (counter_id) REFERENCES public.counters(id);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_priority_id_fkey FOREIGN KEY (priority_id) REFERENCES public.priorities(id);
ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_ticket_type_id_fkey FOREIGN KEY (ticket_type_id) REFERENCES public.ticket_types(id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);
\unrestrict uGEgS6lMmUFugri2RNvApnRJASKpbYXrNivmncPgyn0wrkErfU803opxNggxE9R
