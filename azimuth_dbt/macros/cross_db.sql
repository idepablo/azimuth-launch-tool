{#-
    The few spots where Databricks SQL and DuckDB differ. The daily refresh
    runs on DuckDB in GitHub Actions; the models were built on Databricks and
    still run there. Everything else in the project is the same SQL on both.
-#}

{% macro date_key(col) -%}
    {%- if target.type == 'duckdb' -%}
        cast(strftime({{ col }}, '%Y%m%d') as int)
    {%- else -%}
        cast(date_format({{ col }}, 'yyyyMMdd') as int)
    {%- endif -%}
{%- endmacro %}

{% macro month_name(col) -%}
    {%- if target.type == 'duckdb' -%} monthname({{ col }})
    {%- else -%} date_format({{ col }}, 'MMMM') {%- endif -%}
{%- endmacro %}

{% macro day_name(col) -%}
    {%- if target.type == 'duckdb' -%} dayname({{ col }})
    {%- else -%} date_format({{ col }}, 'EEEE') {%- endif -%}
{%- endmacro %}

{% macro is_weekend(col) -%}
    {#- Databricks weekday(): Monday = 0. DuckDB isodow(): Monday = 1. -#}
    {%- if target.type == 'duckdb' -%} isodow({{ col }}) >= 6
    {%- else -%} weekday({{ col }}) >= 5 {%- endif -%}
{%- endmacro %}

{% macro date_spine(start_date, end_date) -%}
    {%- if target.type == 'duckdb' -%}
        select cast(unnest(generate_series(date '{{ start_date }}', date '{{ end_date }}',
                                           interval 1 day)) as date) as date_day
    {%- else -%}
        select explode(sequence(to_date('{{ start_date }}'), to_date('{{ end_date }}'),
                                interval 1 day)) as date_day
    {%- endif -%}
{%- endmacro %}
