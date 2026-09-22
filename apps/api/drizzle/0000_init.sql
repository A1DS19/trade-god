CREATE TYPE "public"."accrual_zero_factor" AS ENUM('segmentRevenueUsd', 'captureShare', 'accrualPct');--> statement-breakpoint
CREATE TYPE "public"."chain_fact_kind" AS ENUM('pool_census', 'safety', 'issuance', 'holders', 'accrual');--> statement-breakpoint
CREATE TYPE "public"."citation_origin" AS ENUM('human', 'model');--> statement-breakpoint
CREATE TYPE "public"."citation_status" AS ENUM('unverified', 'verified', 'near_miss', 'failed', 'unverifiable_js', 'waived');--> statement-breakpoint
CREATE TYPE "public"."discovery_premium_kind" AS ENUM('MULTIPLE', 'ISSUANCE_NEGATIVE', 'PURE_PREMIUM');--> statement-breakpoint
CREATE TYPE "public"."liquidity_tier" AS ENUM('low', 'medium', 'high');--> statement-breakpoint
CREATE TYPE "public"."provenance_label" AS ENUM('verified', 'vendor_claim');--> statement-breakpoint
CREATE TYPE "public"."report_status" AS ENUM('draft', 'committed');--> statement-breakpoint
CREATE TABLE "chain_facts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"coin_id" uuid NOT NULL,
	"report_id" uuid,
	"kind" "chain_fact_kind" NOT NULL,
	"chain" text NOT NULL,
	"block_number" bigint NOT NULL,
	"fetched_at" timestamp with time zone NOT NULL,
	"payload" jsonb NOT NULL,
	CONSTRAINT "cf_block_number_nonneg" CHECK ("chain_facts"."block_number" >= 0),
	CONSTRAINT "cf_chain_not_blank" CHECK (length(btrim("chain_facts"."chain")) > 0),
	CONSTRAINT "cf_payload_is_object" CHECK (jsonb_typeof("chain_facts"."payload") = 'object')
);
--> statement-breakpoint
CREATE TABLE "citations" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"report_id" uuid NOT NULL,
	"field" text NOT NULL,
	"url" text NOT NULL,
	"quote" text NOT NULL,
	"status" "citation_status" DEFAULT 'unverified' NOT NULL,
	"last_outcome" "citation_status",
	"origin" "citation_origin" NOT NULL,
	"finder_provider" text,
	"finder_model" text,
	"selected_at" timestamp with time zone,
	"verified_at" timestamp with time zone,
	"http_status" integer,
	"matched_offset" integer,
	"waiver_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "ct_field_not_blank" CHECK (length(btrim("citations"."field")) > 0),
	CONSTRAINT "ct_url_not_blank" CHECK (length(btrim("citations"."url")) > 0),
	CONSTRAINT "ct_quote_not_blank" CHECK (length(btrim("citations"."quote")) > 0),
	CONSTRAINT "ct_http_status_range" CHECK ("citations"."http_status" BETWEEN 100 AND 599),
	CONSTRAINT "ct_matched_offset_nonneg" CHECK ("citations"."matched_offset" >= 0),
	CONSTRAINT "ct_waiver_reason_iff_waived" CHECK (("citations"."status" = 'waived') = ("citations"."waiver_reason" IS NOT NULL AND length(btrim("citations"."waiver_reason")) > 0)),
	CONSTRAINT "ct_finder_fields_iff_model" CHECK (("citations"."origin" = 'model') = ("citations"."finder_provider" IS NOT NULL AND "citations"."finder_model" IS NOT NULL)),
	CONSTRAINT "ct_verified_at_iff_resolved" CHECK (("citations"."status" = 'unverified') = ("citations"."verified_at" IS NULL) OR "citations"."status" = 'waived'),
	CONSTRAINT "ct_last_outcome_not_waived" CHECK ("citations"."last_outcome" <> 'waived')
);
--> statement-breakpoint
CREATE TABLE "coins" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"symbol" text NOT NULL,
	"name" text NOT NULL,
	"coingecko_id" text,
	"chain" text NOT NULL,
	"contract_address" text,
	"address_sources" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "coins_symbol_not_blank" CHECK (length(btrim("coins"."symbol")) > 0),
	CONSTRAINT "coins_name_not_blank" CHECK (length(btrim("coins"."name")) > 0),
	CONSTRAINT "coins_chain_not_blank" CHECK (length(btrim("coins"."chain")) > 0),
	CONSTRAINT "coins_address_sources_min_2" CHECK (CASE
            WHEN jsonb_typeof("coins"."address_sources") <> 'array' THEN false
            WHEN "coins"."contract_address" IS NULL THEN true
            ELSE jsonb_array_length("coins"."address_sources") >= 2
          END)
);
--> statement-breakpoint
CREATE TABLE "forward_returns" (
	"report_id" uuid NOT NULL,
	"horizon_days" integer NOT NULL,
	"price_at_commit_usd" double precision NOT NULL,
	"price_at_horizon_usd" double precision NOT NULL,
	"price_source" text NOT NULL,
	"priced_at" timestamp with time zone NOT NULL,
	"return_fraction" double precision GENERATED ALWAYS AS ((price_at_horizon_usd / price_at_commit_usd) - 1) STORED NOT NULL,
	"computed_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "forward_returns_report_id_horizon_days_pk" PRIMARY KEY("report_id","horizon_days"),
	CONSTRAINT "fr_horizon_frozen" CHECK ("forward_returns"."horizon_days" IN (30, 90, 180, 365)),
	CONSTRAINT "fr_commit_price_positive" CHECK ("forward_returns"."price_at_commit_usd" > 0 AND "forward_returns"."price_at_commit_usd" < 'Infinity'::float8),
	CONSTRAINT "fr_horizon_price_nonneg" CHECK ("forward_returns"."price_at_horizon_usd" >= 0 AND "forward_returns"."price_at_horizon_usd" < 'Infinity'::float8),
	CONSTRAINT "fr_price_source_not_blank" CHECK (length(btrim("forward_returns"."price_source")) > 0)
);
--> statement-breakpoint
CREATE TABLE "report_scores" (
	"report_id" uuid PRIMARY KEY NOT NULL,
	"scoring_version" text,
	"overview_sentence" text,
	"risk_notes" text,
	"product_ease" integer,
	"product_hair_fire" integer,
	"product_exclusivity" integer,
	"product_total" integer,
	"product_passed" boolean,
	"product_ease_rationale" text,
	"product_hair_fire_rationale" text,
	"product_exclusivity_rationale" text,
	"liquidity_tier" "liquidity_tier",
	"liquidity_tier_assigned_at" timestamp with time zone,
	"liquidity_justification" text,
	"liquidity_depth_2pct_usd" double precision,
	"liquidity_depth_source" text,
	"liquidity_depth_url" text,
	"liquidity_depth_label" "provenance_label",
	"liquidity_depth_measured_at" timestamp with time zone,
	"liquidity_top_pool_tvl_usd" double precision,
	"liquidity_top_pool_source" text,
	"liquidity_top_pool_url" text,
	"liquidity_top_pool_label" "provenance_label",
	"liquidity_top_pool_measured_at" timestamp with time zone,
	"liquidity_no_dex_pool" boolean DEFAULT false NOT NULL,
	"liquidity_surviving_pools" integer,
	"narrative_maturity" integer,
	"narrative_smart_money" integer,
	"narrative_hair_fire" integer,
	"narrative_communication" integer,
	"narrative_lineage" integer,
	"narrative_mutation" integer,
	"narrative_total" integer,
	"narrative_maturity_rationale" text,
	"narrative_smart_money_rationale" text,
	"narrative_hair_fire_rationale" text,
	"narrative_communication_rationale" text,
	"narrative_lineage_rationale" text,
	"narrative_mutation_rationale" text,
	"team_weighted_score" double precision,
	"accrual_segment_revenue_usd" double precision,
	"accrual_capture_share" double precision,
	"accrual_pct" double precision,
	"accrual_annual_issuance_usd" double precision,
	"accrual_assessed" boolean GENERATED ALWAYS AS (accrual_segment_revenue_usd IS NOT NULL
            AND accrual_capture_share IS NOT NULL
            AND accrual_pct IS NOT NULL
            AND accrual_annual_issuance_usd IS NOT NULL) STORED NOT NULL,
	"accrual_absent_reason" text,
	"accrual_rationale" text,
	"accrual_gross_annual_flow_usd" double precision,
	"accrual_net_annual_flow_usd" double precision,
	"accrual_zero_factor" "accrual_zero_factor",
	"accrual_contract_address" text,
	"accrual_finding" text,
	"accrual_measured_trailing_90d_usd" double precision,
	"discovery_market_cap_usd" double precision,
	"discovery_market_cap_source" text,
	"discovery_market_cap_url" text,
	"discovery_market_cap_label" "provenance_label",
	"discovery_market_cap_measured_at" timestamp with time zone,
	"discovery_premium_kind" "discovery_premium_kind",
	"discovery_premium_multiple" double precision,
	"waived_citation_count" integer,
	CONSTRAINT "rs_product_ease_range" CHECK ("report_scores"."product_ease" BETWEEN 0 AND 10),
	CONSTRAINT "rs_product_hair_fire_range" CHECK ("report_scores"."product_hair_fire" BETWEEN 0 AND 10),
	CONSTRAINT "rs_product_exclusivity_range" CHECK ("report_scores"."product_exclusivity" BETWEEN 0 AND 10),
	CONSTRAINT "rs_narrative_maturity_range" CHECK ("report_scores"."narrative_maturity" BETWEEN 0 AND 7),
	CONSTRAINT "rs_narrative_smart_money_range" CHECK ("report_scores"."narrative_smart_money" BETWEEN 0 AND 6),
	CONSTRAINT "rs_narrative_hair_fire_range" CHECK ("report_scores"."narrative_hair_fire" BETWEEN 0 AND 6),
	CONSTRAINT "rs_narrative_communication_range" CHECK ("report_scores"."narrative_communication" BETWEEN 0 AND 5),
	CONSTRAINT "rs_narrative_lineage_range" CHECK ("report_scores"."narrative_lineage" BETWEEN 0 AND 4),
	CONSTRAINT "rs_narrative_mutation_range" CHECK ("report_scores"."narrative_mutation" BETWEEN 0 AND 3),
	CONSTRAINT "rs_team_weighted_range" CHECK ("report_scores"."team_weighted_score" BETWEEN 0 AND 10),
	CONSTRAINT "rs_segment_revenue_nonneg" CHECK ("report_scores"."accrual_segment_revenue_usd" >= 0 AND "report_scores"."accrual_segment_revenue_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_capture_share_unit" CHECK ("report_scores"."accrual_capture_share" BETWEEN 0 AND 1),
	CONSTRAINT "rs_accrual_pct_unit" CHECK ("report_scores"."accrual_pct" BETWEEN 0 AND 1),
	CONSTRAINT "rs_annual_issuance_nonneg" CHECK ("report_scores"."accrual_annual_issuance_usd" >= 0 AND "report_scores"."accrual_annual_issuance_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_gross_flow_nonneg" CHECK ("report_scores"."accrual_gross_annual_flow_usd" >= 0 AND "report_scores"."accrual_gross_annual_flow_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_net_flow_finite" CHECK ("report_scores"."accrual_net_annual_flow_usd" > '-Infinity'::float8 AND "report_scores"."accrual_net_annual_flow_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_market_cap_nonneg" CHECK ("report_scores"."discovery_market_cap_usd" >= 0 AND "report_scores"."discovery_market_cap_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_premium_multiple_nonneg" CHECK ("report_scores"."discovery_premium_multiple" >= 0 AND "report_scores"."discovery_premium_multiple" < 'Infinity'::float8),
	CONSTRAINT "rs_measured_90d_nonneg" CHECK ("report_scores"."accrual_measured_trailing_90d_usd" >= 0 AND "report_scores"."accrual_measured_trailing_90d_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_depth_2pct_nonneg" CHECK ("report_scores"."liquidity_depth_2pct_usd" >= 0 AND "report_scores"."liquidity_depth_2pct_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_top_pool_tvl_nonneg" CHECK ("report_scores"."liquidity_top_pool_tvl_usd" >= 0 AND "report_scores"."liquidity_top_pool_tvl_usd" < 'Infinity'::float8),
	CONSTRAINT "rs_surviving_pools_nonneg" CHECK ("report_scores"."liquidity_surviving_pools" >= 0),
	CONSTRAINT "rs_waived_count_nonneg" CHECK ("report_scores"."waived_citation_count" >= 0),
	CONSTRAINT "rs_scoring_version_not_blank" CHECK (length(btrim("report_scores"."scoring_version")) > 0),
	CONSTRAINT "rs_scored_row_names_its_version" CHECK (("report_scores"."product_passed" IS NULL) = ("report_scores"."scoring_version" IS NULL)),
	CONSTRAINT "rs_product_total_is_sum" CHECK (CASE WHEN "report_scores"."product_passed" IS NULL THEN true ELSE
            "report_scores"."product_total" = "report_scores"."product_ease" + "report_scores"."product_hair_fire" + "report_scores"."product_exclusivity"
          END),
	CONSTRAINT "rs_product_passed_matches_threshold" CHECK (CASE WHEN "report_scores"."product_passed" IS NULL THEN true ELSE
            "report_scores"."product_passed" = ("report_scores"."product_total" >= 16)
          END),
	CONSTRAINT "rs_narrative_total_is_sum" CHECK (CASE WHEN "report_scores"."product_passed" IS NULL OR "report_scores"."narrative_total" IS NULL THEN true ELSE
            "report_scores"."narrative_total" = "report_scores"."narrative_maturity" + "report_scores"."narrative_smart_money"
              + "report_scores"."narrative_hair_fire" + "report_scores"."narrative_communication"
              + "report_scores"."narrative_lineage" + "report_scores"."narrative_mutation"
          END),
	CONSTRAINT "rs_gross_flow_is_product" CHECK (CASE WHEN "report_scores"."accrual_gross_annual_flow_usd" IS NULL THEN true ELSE
            "report_scores"."accrual_gross_annual_flow_usd"
              = "report_scores"."accrual_segment_revenue_usd" * "report_scores"."accrual_capture_share" * "report_scores"."accrual_pct"
          END),
	CONSTRAINT "rs_net_flow_is_gross_minus_issuance" CHECK (CASE WHEN "report_scores"."accrual_net_annual_flow_usd" IS NULL THEN true ELSE
            "report_scores"."accrual_net_annual_flow_usd"
              = "report_scores"."accrual_gross_annual_flow_usd" - "report_scores"."accrual_annual_issuance_usd"
          END),
	CONSTRAINT "rs_zero_factor_matches_inputs" CHECK (CASE WHEN "report_scores"."product_passed" IS NULL THEN true ELSE
            "report_scores"."accrual_zero_factor" IS NOT DISTINCT FROM (
              CASE
                WHEN "report_scores"."accrual_segment_revenue_usd" = 0 THEN 'segmentRevenueUsd'
                WHEN "report_scores"."accrual_capture_share" = 0 THEN 'captureShare'
                WHEN "report_scores"."accrual_pct" = 0 THEN 'accrualPct'
                ELSE NULL
              END)::accrual_zero_factor
          END),
	CONSTRAINT "rs_premium_kind_matches_flows" CHECK ("report_scores"."discovery_premium_kind" IS NOT DISTINCT FROM (
            CASE
              WHEN "report_scores"."accrual_net_annual_flow_usd" IS NULL THEN NULL
              WHEN "report_scores"."accrual_net_annual_flow_usd" > 0
                   AND "report_scores"."accrual_net_annual_flow_usd" >= "report_scores"."accrual_gross_annual_flow_usd" * 1e-9
                THEN 'MULTIPLE'
              WHEN "report_scores"."accrual_gross_annual_flow_usd" > 0 THEN 'ISSUANCE_NEGATIVE'
              ELSE 'PURE_PREMIUM'
            END)::discovery_premium_kind),
	CONSTRAINT "rs_premium_multiple_iff_multiple" CHECK (("report_scores"."discovery_premium_kind" = 'MULTIPLE') = ("report_scores"."discovery_premium_multiple" IS NOT NULL)),
	CONSTRAINT "rs_premium_multiple_is_quotient" CHECK (CASE WHEN "report_scores"."discovery_premium_multiple" IS NULL THEN true ELSE
            "report_scores"."discovery_premium_multiple"
              = "report_scores"."discovery_market_cap_usd" / "report_scores"."accrual_net_annual_flow_usd"
          END),
	CONSTRAINT "rs_premium_needs_assessment" CHECK ("report_scores"."accrual_assessed" OR "report_scores"."discovery_premium_kind" IS NULL),
	CONSTRAINT "rs_depth_provenance_complete" CHECK (("report_scores"."liquidity_depth_2pct_usd" IS NOT NULL) = (
            "report_scores"."liquidity_depth_source" IS NOT NULL AND "report_scores"."liquidity_depth_url" IS NOT NULL
            AND "report_scores"."liquidity_depth_label" IS NOT NULL
            AND "report_scores"."liquidity_depth_measured_at" IS NOT NULL)),
	CONSTRAINT "rs_top_pool_provenance_complete" CHECK (("report_scores"."liquidity_top_pool_tvl_usd" IS NOT NULL) = (
            "report_scores"."liquidity_top_pool_source" IS NOT NULL AND "report_scores"."liquidity_top_pool_url" IS NOT NULL
            AND "report_scores"."liquidity_top_pool_label" IS NOT NULL
            AND "report_scores"."liquidity_top_pool_measured_at" IS NOT NULL)),
	CONSTRAINT "rs_market_cap_provenance_complete" CHECK (("report_scores"."discovery_market_cap_usd" IS NOT NULL) = (
            "report_scores"."discovery_market_cap_source" IS NOT NULL AND "report_scores"."discovery_market_cap_url" IS NOT NULL
            AND "report_scores"."discovery_market_cap_label" IS NOT NULL
            AND "report_scores"."discovery_market_cap_measured_at" IS NOT NULL)),
	CONSTRAINT "rs_no_dex_pool_excludes_tvl" CHECK (NOT ("report_scores"."liquidity_no_dex_pool" AND "report_scores"."liquidity_top_pool_tvl_usd" IS NOT NULL)),
	CONSTRAINT "rs_tier_assigned_at_iff_tier" CHECK (("report_scores"."liquidity_tier" IS NULL) = ("report_scores"."liquidity_tier_assigned_at" IS NULL)),
	CONSTRAINT "rs_tier_not_older_than_its_inputs" CHECK (("report_scores"."liquidity_tier_assigned_at" IS NULL
           OR "report_scores"."liquidity_depth_measured_at" IS NULL
           OR "report_scores"."liquidity_tier_assigned_at" >= "report_scores"."liquidity_depth_measured_at")
          AND ("report_scores"."liquidity_tier_assigned_at" IS NULL
           OR "report_scores"."liquidity_top_pool_measured_at" IS NULL
           OR "report_scores"."liquidity_tier_assigned_at" >= "report_scores"."liquidity_top_pool_measured_at")),
	CONSTRAINT "rs_gate_completeness" CHECK (CASE WHEN "report_scores"."product_passed" THEN
            length(btrim(coalesce("report_scores"."overview_sentence", ''))) > 0
            AND length(btrim(coalesce("report_scores"."product_ease_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."product_hair_fire_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."product_exclusivity_rationale", ''))) > 0
            AND "report_scores"."liquidity_tier" IS NOT NULL
            AND length(btrim(coalesce("report_scores"."liquidity_justification", ''))) > 0
            AND "report_scores"."liquidity_depth_2pct_usd" IS NOT NULL
            AND ("report_scores"."liquidity_top_pool_tvl_usd" IS NOT NULL OR "report_scores"."liquidity_no_dex_pool")
            AND "report_scores"."narrative_maturity" IS NOT NULL
            AND "report_scores"."narrative_smart_money" IS NOT NULL
            AND "report_scores"."narrative_hair_fire" IS NOT NULL
            AND "report_scores"."narrative_communication" IS NOT NULL
            AND "report_scores"."narrative_lineage" IS NOT NULL
            AND "report_scores"."narrative_mutation" IS NOT NULL
            AND "report_scores"."narrative_total" IS NOT NULL
            AND length(btrim(coalesce("report_scores"."narrative_maturity_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."narrative_smart_money_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."narrative_hair_fire_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."narrative_communication_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."narrative_lineage_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."narrative_mutation_rationale", ''))) > 0
            AND "report_scores"."team_weighted_score" IS NOT NULL
            AND length(btrim(coalesce("report_scores"."accrual_rationale", ''))) > 0
            AND length(btrim(coalesce("report_scores"."risk_notes", ''))) > 0
            AND "report_scores"."waived_citation_count" IS NOT NULL
            AND CASE WHEN "report_scores"."accrual_assessed"
                  THEN "report_scores"."accrual_gross_annual_flow_usd" IS NOT NULL
                       AND "report_scores"."accrual_net_annual_flow_usd" IS NOT NULL
                       AND "report_scores"."discovery_market_cap_usd" IS NOT NULL
                       AND "report_scores"."discovery_premium_kind" IS NOT NULL
                  ELSE length(btrim(coalesce("report_scores"."accrual_absent_reason", ''))) > 0
                END
          ELSE true END)
);
--> statement-breakpoint
CREATE TABLE "report_team" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"report_id" uuid NOT NULL,
	"position" integer NOT NULL,
	"name" text NOT NULL,
	"name_key" text GENERATED ALWAYS AS (lower(btrim(regexp_replace(name, '[[:space:]]+', ' ', 'g')))) STORED NOT NULL,
	"roles" text[] NOT NULL,
	"is_founder" boolean NOT NULL,
	"h" integer NOT NULL,
	"m" integer NOT NULL,
	"l" integer NOT NULL,
	"summary" text NOT NULL,
	CONSTRAINT "rt_h_range" CHECK ("report_team"."h" BETWEEN 0 AND 5),
	CONSTRAINT "rt_m_range" CHECK ("report_team"."m" BETWEEN 0 AND 3),
	CONSTRAINT "rt_l_range" CHECK ("report_team"."l" BETWEEN 0 AND 2),
	CONSTRAINT "rt_position_positive" CHECK ("report_team"."position" >= 1),
	CONSTRAINT "rt_name_not_blank" CHECK (length(btrim("report_team"."name")) > 0),
	CONSTRAINT "rt_roles_not_empty" CHECK (array_length("report_team"."roles", 1) >= 1),
	CONSTRAINT "rt_summary_not_blank" CHECK (length(btrim("report_team"."summary")) > 0)
);
--> statement-breakpoint
CREATE TABLE "reports" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"coin_id" uuid NOT NULL,
	"version" integer DEFAULT 1 NOT NULL,
	"status" "report_status" DEFAULT 'draft' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"committed_at" timestamp with time zone,
	"coin_symbol" text,
	"coin_chain" text,
	"coin_contract_address" text,
	CONSTRAINT "reports_version_positive" CHECK ("reports"."version" >= 1),
	CONSTRAINT "reports_committed_at_iff_committed" CHECK (("reports"."status" = 'committed') = ("reports"."committed_at" IS NOT NULL)),
	CONSTRAINT "reports_identity_snapshot_iff_committed" CHECK (("reports"."status" = 'committed')
          = ("reports"."coin_symbol" IS NOT NULL AND "reports"."coin_chain" IS NOT NULL))
);
--> statement-breakpoint
ALTER TABLE "chain_facts" ADD CONSTRAINT "chain_facts_coin_id_coins_id_fk" FOREIGN KEY ("coin_id") REFERENCES "public"."coins"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "chain_facts" ADD CONSTRAINT "chain_facts_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "citations" ADD CONSTRAINT "citations_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "forward_returns" ADD CONSTRAINT "forward_returns_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "report_scores" ADD CONSTRAINT "report_scores_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "report_team" ADD CONSTRAINT "report_team_report_id_reports_id_fk" FOREIGN KEY ("report_id") REFERENCES "public"."reports"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "reports" ADD CONSTRAINT "reports_coin_id_coins_id_fk" FOREIGN KEY ("coin_id") REFERENCES "public"."coins"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "cf_coin_kind_idx" ON "chain_facts" USING btree ("coin_id","kind");--> statement-breakpoint
CREATE INDEX "cf_report_id_idx" ON "chain_facts" USING btree ("report_id");--> statement-breakpoint
CREATE INDEX "ct_report_id_idx" ON "citations" USING btree ("report_id");--> statement-breakpoint
CREATE INDEX "ct_report_selected_idx" ON "citations" USING btree ("report_id","status") WHERE "citations"."selected_at" IS NOT NULL;--> statement-breakpoint
CREATE INDEX "ct_finder_idx" ON "citations" USING btree ("finder_provider","finder_model") WHERE "citations"."origin" = 'model';--> statement-breakpoint
CREATE UNIQUE INDEX "coins_chain_address_uniq" ON "coins" USING btree ("chain",lower("contract_address")) WHERE "coins"."contract_address" IS NOT NULL;--> statement-breakpoint
CREATE INDEX "coins_symbol_idx" ON "coins" USING btree ("symbol");--> statement-breakpoint
CREATE UNIQUE INDEX "rt_report_position_uniq" ON "report_team" USING btree ("report_id","position");--> statement-breakpoint
CREATE UNIQUE INDEX "rt_report_name_key_uniq" ON "report_team" USING btree ("report_id","name_key");--> statement-breakpoint
CREATE UNIQUE INDEX "rt_one_founder_per_report" ON "report_team" USING btree ("report_id") WHERE "report_team"."is_founder";--> statement-breakpoint
CREATE INDEX "rt_report_id_idx" ON "report_team" USING btree ("report_id");--> statement-breakpoint
CREATE INDEX "reports_coin_id_idx" ON "reports" USING btree ("coin_id");--> statement-breakpoint
CREATE INDEX "reports_committed_idx" ON "reports" USING btree ("committed_at") WHERE "reports"."status" = 'committed';