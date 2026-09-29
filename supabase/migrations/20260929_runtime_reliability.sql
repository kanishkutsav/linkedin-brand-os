-- Keep the learning semantic-search function compatible with the
-- installed pgvector extension and explicit extensions schema.
create extension if not exists vector with schema extensions;

create or replace function public.match_learning_events(
    p_profile_id integer,
    p_query_embedding extensions.vector,
    p_match_threshold double precision default 0.45,
    p_match_count integer default 8
)
returns table(
    id bigint,
    event_type varchar,
    source_type varchar,
    source_id varchar,
    content text,
    metadata_json text,
    created_at timestamptz,
    similarity double precision
)
language sql
stable
set search_path = public, extensions, pg_temp
as $function$
    select
        e.id,
        e.event_type,
        e.source_type,
        e.source_id,
        e.content,
        e.metadata_json,
        e.created_at,
        1 - (e.embedding <=> p_query_embedding)
    from public.learning_events e
    where e.profile_id = p_profile_id
      and e.embedding is not null
      and 1 - (e.embedding <=> p_query_embedding) >= p_match_threshold
    order by e.embedding <=> p_query_embedding asc
    limit least(greatest(p_match_count, 1), 50);
$function$;
