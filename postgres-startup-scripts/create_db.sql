-- create a new database
CREATE DATABASE tradingdata;

BEGIN;

-- try to connect to the new database
\c tradingdata

-- create a role with connect privileges to the warehouse
CREATE ROLE green NOLOGIN;

-- create a new operational role
CREATE ROLE anonymous LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD 'fedjikrejnkifdngkjrew';

-- grant green to anonymous
GRANT green TO anonymous;

-- revoke connections from public to the database
REVOKE ALL ON DATABASE tradingdata FROM public;

-- grant connect privileges to green
GRANT CONNECT ON DATABASE tradingdata to green;

-- revoke all permissions from public schema
REVOKE ALL ON SCHEMA public FROM public;

-- grant access on schema public
GRANT USAGE ON SCHEMA public to green;

----------------------------------
-- public.candle_stick_five_min --
----------------------------------
CREATE TABLE public.candle_stick_five_min (
id             BIGINT                           NOT NULL       GENERATED ALWAYS AS IDENTITY,
currency_pair  TEXT                             NOT NULL,
open_price     NUMERIC                          NOT NULL,
high_price     NUMERIC                          NOT NULL,
low_price      NUMERIC                          NOT NULL,
close_price    NUMERIC                          NOT NULL,
open_time      TIMESTAMP WITHOUT TIME ZONE      NOT NULL,
close_time     TIMESTAMP WITHOUT TIME ZONE      NOT NULL,
CONSTRAINT pk_candle_stick_five_min PRIMARY KEY (id)
);

CREATE INDEX idx_candle_stick_five_min_1 ON candle_stick_five_min (open_time);
CREATE INDEX idx_candle_stick_five_min_2 ON candle_stick_five_min (currency_pair);

-- grant privileges to green
GRANT SELECT, INSERT, UPDATE, DELETE ON candle_stick_five_min to green;

COMMIT;
