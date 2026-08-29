{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- In CI, everything builds into the isolated target schema.
        Elsewhere, declared schemas are used literally. -#}
    {%- if target.name == 'ci' or custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}