CREATE DATABASE IF NOT EXISTS aicookDB;
USE aicookDB;






CREATE TABLE IF NOT EXISTS categorie (
  id_categoria INT          NOT NULL AUTO_INCREMENT,
  nome         VARCHAR(100) NOT NULL,
  descrizione  TEXT         DEFAULT NULL,
  created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_categoria),
  UNIQUE KEY uq_categoria_nome (nome)
) ;






CREATE TABLE IF NOT EXISTS ricette (
  id_ricetta    INT           NOT NULL AUTO_INCREMENT,
  nome          VARCHAR(255)  NOT NULL,
  id_categoria  INT           DEFAULT NULL,
  procedimento  LONGTEXT      NOT NULL,
  tempo_prep    INT UNSIGNED  DEFAULT NULL,
  tempo_cottura INT UNSIGNED  DEFAULT NULL,
  difficolta    VARCHAR(10)   DEFAULT 'media',
  porzioni      INT UNSIGNED  DEFAULT 4,
  chunk_vs_path VARCHAR(500)  DEFAULT NULL,
  embedding_id  VARCHAR(100)  DEFAULT NULL,
  sorgente_pdf  VARCHAR(300)  DEFAULT NULL,
  created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id_ricetta),
  FOREIGN KEY (id_categoria) REFERENCES categorie(id_categoria)
    ON DELETE SET NULL ON UPDATE CASCADE,
  INDEX idx_difficolta (difficolta),
  INDEX idx_categoria  (id_categoria),
  FULLTEXT INDEX ft_ricetta (nome, procedimento)
) ;




CREATE TABLE IF NOT EXISTS ingredienti (
  id_ingrediente INT          NOT NULL AUTO_INCREMENT,
  nome           VARCHAR(150) NOT NULL,
  unita_misura   VARCHAR(30)  DEFAULT NULL,
  created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_ingrediente),
  UNIQUE KEY uq_ingrediente_nome (nome),
  INDEX idx_nome_ing (nome)
) ;






CREATE TABLE IF NOT EXISTS ricetta_ingredienti (
  id             INT           NOT NULL AUTO_INCREMENT,
  id_ricetta     INT           NOT NULL,
  id_ingrediente INT           NOT NULL,
  quantita       DECIMAL(8,2)  DEFAULT NULL,
  note           VARCHAR(100)  DEFAULT NULL,
  ordine         INT UNSIGNED  DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ricetta_ing (id_ricetta, id_ingrediente),
  FOREIGN KEY (id_ricetta)     REFERENCES ricette(id_ricetta)
    ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (id_ingrediente) REFERENCES ingredienti(id_ingrediente)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ;


CREATE TABLE IF NOT EXISTS query_log (
  id_query    INT         NOT NULL AUTO_INCREMENT,
  testo_query TEXT        NOT NULL,
  risposta_ai LONGTEXT    DEFAULT NULL,
  id_ricetta  INT         DEFAULT NULL,
  ip_client   VARCHAR(45) DEFAULT NULL,
  created_at  TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_query),
  FOREIGN KEY (id_ricetta) REFERENCES ricette(id_ricetta)
    ON DELETE SET NULL ON UPDATE CASCADE,
  INDEX idx_created (created_at)
) ;






INSERT INTO categorie (nome, descrizione) VALUES
  ('Antipasto', 'Piatti serviti prima del pasto'),
  ('Primo',     'Pasta, riso, zuppe'),
  ('Secondo',   'Carne, pesce, legumi'),
  ('Contorno',  'Verdure e accompagnamenti'),
  ('Dolce',     'Dessert e dolci'),
  ('Bevanda',   'Drinks');