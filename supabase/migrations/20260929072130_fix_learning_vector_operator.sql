-- Repair learning vector RPCs for Supabase's extensions-schema pgvector.
-- Keep operator resolution explicit so these functions remain correct even when
-- the runtime role's search_path does not include the extensions schema.
create or replace function public.match_learning_events(
    p_profile_id integer,
    p_query_embedding extensions.vector(768),
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
set search_path to 'public', 'pg_temp'
as $function$
    select
        e.id,
        e.event_type,
        e.source_type,
        e.source_id,
        e.content,
        e.metadata_json,
        e.created_at,
        1 - (e.embedding operator(extensions.<=>) p_query_embedding)
    from public.learning_events e
    where e.profile_id = p_profile_id
      and e.embedding is not null
      and 1 - (e.embedding operator(extensions.<=>) p_query_embedding) >= p_match_threshold
    order by e.embedding operator(extensions.<=>) p_query_embedding asc
    limit least(greatest(p_match_count, 1), 50);
$function$;

create or replace function public.match_learning_memories(
    p_profile_id integer,
    p_query_embedding extensions.vector(768),
    p_match_threshold double precision default 0.45,
    p_match_count integer default 8
)
returns table(
    id bigint,
    memory_key varchar,
    memory_type varchar,
    content text,
    confidence varchar,
    importance double precision,
    source_count integer,
    metadata_json text,
    updated_at timestamptz,
    similarity double precision
)
language sql
stable
set search_path to 'public', 'pg_temp'
as $function$
    select
        m.id,
        m.memory_key,
        m.memory_type,
        m.content,
        m.confidence,
        m.importance,
        m.source_count,
        m.metadata_json,
        m.updated_at,
        1 - (m.embedding operator(extensions.<=>) p_query_embedding)
    from public.learning_memories m
    where m.profile_id = p_profile_id
      and m.embedding is not null
      and 1 - (m.embedding operator(extensions.<=>) p_query_embedding) >= p_match_threshold
    order by m.embedding operator(extensions.<=>) p_query_embedding asc
    limit least(greatest(p_match_count, 1), 50);
$function$;
