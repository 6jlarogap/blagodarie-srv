# Generated by Django 3.2.6 on 2022-09-29 14:23

from django.db import migrations, connection

# Функции postgres поиска по довериям, по родственным связям
#
# Attribution:
# https://www.alibabacloud.com/blog/applying-postgresql-graph-database-to-social-scenarios_595035


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    ops = """
drop function find_rel_mother_father(int, int, bool, bool)
\f
drop function find_shortest_relation_path(int, int, int)
\f
drop function find_trust_relation_path(int, int, int)
\f
drop function find_rel_trust(int, int)
\f
drop table template_tmp_links
\f
drop table template_tmp_trust
\f
drop table template_tmp_parent
\f
create temp table tmp_links(
    level int,
    user_from_id int,
    user_to_id int
) ON COMMIT delete rows;
\f
create unlogged table template_tmp_links (like tmp_links)
\f
create temp table tmp_links_paths(
    level int,
    path int[],
    user_from_id int,
    user_to_id int
) ON COMMIT delete rows;
\f
create unlogged table template_tmp_links_paths (like tmp_links_paths)
\f
create function find_trust_tree(
    v_user_from_id int,
    v_level int
) returns setof template_tmp_links as 
$$

-- Дерево доверий, начиная с пользователя v_user_from_id
--  v_level:
--      максимальное число итераций при проходе по дереву связей
--

declare 
    i int := 1;
begin 
    if v_level <= 0 then 
        raise notice 'level must >= 1'; 
        return; 
    end if; 
  
    create temp table tmp(like template_tmp_links) ON COMMIT delete rows;
    create index if not exists idx_tmp_trust_1 on tmp(level);
    create index if not exists idx_tmp_trust_2 on tmp(user_from_id);
    create index if not exists idx_tmp_trust_3 on tmp(user_to_id);

    return query
        insert into tmp
            select
                i,
                user_from_id,
                user_to_id
            from
                contact_currentstate
            where
                user_from_id=v_user_from_id and
                contact_currentstate.is_trust and
                user_to_id is not null
    returning *;

    loop
        i := i + 1; 

        -- All levels of data has been found
        if i > v_level then
            return;
        end if; 

        -- The next level relation is derived though a join with level=i-1
        -- (Group By excludes duplicate nodes.
        -- For example, 3 in 1-2-3-4 and 1-5-3-4 is excluded),
        -- and the looping points are excluded by not exists.
        --
        return query 
            insert into tmp
                select
                    i,
                    contact_currentstate.user_from_id,
                    contact_currentstate.user_to_id
                from
                    contact_currentstate
                join
                    (select user_to_id from tmp where level = i - 1 group by user_to_id)
                tmp on
                    (contact_currentstate.user_from_id = tmp.user_to_id)
                where
                    contact_currentstate.user_to_id is not null and
                    contact_currentstate.is_trust and
                not exists (
                    select 1 from tmp where contact_currentstate.user_from_id = tmp.user_from_id
                )
        returning *;
  end loop; 
end;

$$
    language plpgsql strict
\f
create or replace function find_genesis_tree(
    v_user_from_id int,
    v_level int,
    v_all boolean,
    v_is_child boolean
) returns setof template_tmp_links as 
$$

-- Родственное дерево, начиная с пользователя v_user_from_id
--  v_level:
--      максимальное число итераций при проходе по дереву связей
--  v_all:
--      показывать ли все связи, то есть проходим и по потомкам,
--      и по предкам, получаем в т.ч. тетей, двоюродных и т.д.
--      Если True, то v_is_child роли не играет
--  v_is_child:
--      При v_all == False:
--          v_is_child == True:     проходим только по детям.
--          v_is_child == False:    проходим только по предкам.
--

declare 
    i int := 1;
begin 
    if v_level <= 0 then 
        raise notice 'level must >= 1'; 
        return; 
    end if; 
  
    create temp table if not exists tmp(like template_tmp_links) ON COMMIT delete rows;
    create index if not exists idx_tmp_parent_1 on tmp(level);
    create index if not exists idx_tmp_parent_2 on tmp(user_from_id);
    create index if not exists idx_tmp_parent_3 on tmp(user_to_id);

    return query 
        insert into tmp
            select
                i,
                user_from_id,
                user_to_id
            from
                contact_currentstate
            where
                user_from_id=v_user_from_id and
                (
                    contact_currentstate.is_father or
                    contact_currentstate.is_mother
                ) and
                (
                    v_all or
                    is_child = v_is_child
                )
                and
                user_to_id is not null
    returning *;

    loop
        i := i+1; 

        -- All levels of data has been found
        if i > v_level then
            return;
        end if; 

        -- The next level relation is derived though a join with level=i-1
        -- (Group By excludes duplicate nodes.
        -- For example, 3 in 1-2-3-4 and 1-5-3-4 is excluded),
        -- and the looping points are excluded by not exists.
        --
        return query 
            insert into tmp
                select
                    i,
                    contact_currentstate.user_from_id,
                    contact_currentstate.user_to_id
                from
                    contact_currentstate
                join
                    (select user_to_id from tmp where level = i - 1 group by user_to_id)
                tmp on
                    (contact_currentstate.user_from_id = tmp.user_to_id)
                where
                    contact_currentstate.user_to_id is not null and
                (
                    contact_currentstate.is_father or
                    contact_currentstate.is_mother
                ) and
                (
                    v_all or
                    is_child = v_is_child
                ) and
                not exists (
                    select 1 from tmp where contact_currentstate.user_from_id = tmp.user_from_id
                )
        returning *;
  end loop; 
end;

$$
    language plpgsql strict
\f
create function find_trust_path_shortest(
    v_user_from_id int,
    v_user_to_id int,
    v_level int
) returns setof template_tmp_links_paths as 
$$
declare 
    i int := 1; 
begin 
    if v_level <= 0 then 
        raise notice 'level must >= 1'; 
        return; 
    end if; 
  
    create temp table if not exists tmp(like template_tmp_links_paths) ON COMMIT delete rows;
    create index if not exists idx_tmp_links_1 on tmp(level);
    create index if not exists idx_tmp_links_2 on tmp(user_from_id);
    create index if not exists idx_tmp_links_3 on tmp(user_to_id);

    return query
        insert into tmp
            select
                i,
                array[]::int[] || user_from_id || user_to_id,
                user_from_id,
                user_to_id
            from
                contact_currentstate
            where
                user_from_id = v_user_from_id and
                contact_currentstate.is_trust and
                user_to_id is not null
    returning *; 

    loop
        i := i + 1; 
        if i > v_level then
            return;
        end if; 

        if exists (
            select
                1
            from
                tmp
            where
                user_to_id = v_user_to_id and
                level = i - 1
        ) then
            return;
        end if;

        return query
            insert into tmp
                select
                    i,
                    tmp.path || contact_currentstate.user_to_id,
                    contact_currentstate.user_from_id,
                    contact_currentstate.user_to_id
                from
                    contact_currentstate
                join
                    (select user_to_id, path from tmp where level = i - 1)
                tmp on
                    (contact_currentstate.user_from_id = tmp.user_to_id)
                where
                    contact_currentstate.user_to_id is not null and
                    contact_currentstate.is_trust and
                    not exists (
                        select
                            1
                        from
                            tmp
                        where
                            contact_currentstate.user_from_id = tmp.user_from_id
                    )
        returning *; 
    end loop; 
end;

$$
    language plpgsql strict
\f
create or replace function find_genesis_path_shortest(
    v_user_from_id int,
    v_user_to_id int,
    v_level int
) returns setof template_tmp_links_paths as 
$$
declare 
    i int := 1; 
begin 
    if v_level <= 0 then 
        raise notice 'level must >= 1'; 
        return; 
    end if; 
  
    create temp table if not exists tmp(like template_tmp_links_paths) ON COMMIT delete rows;
    create index if not exists idx_tmp_links_1 on tmp(level);
    create index if not exists idx_tmp_links_2 on tmp(user_from_id);
    create index if not exists idx_tmp_links_3 on tmp(user_to_id);

    return query
        insert into tmp
            select
                i,
                array[]::int[] || user_from_id || user_to_id,
                user_from_id,
                user_to_id
            from
                contact_currentstate
            where
                user_from_id = v_user_from_id and
                (
                    contact_currentstate.is_father or
                    contact_currentstate.is_mother
                ) and
                user_to_id is not null
    returning *; 

    loop
        i := i + 1; 
        if i > v_level then
            return;
        end if; 

        if exists (
            select
                1
            from
                tmp
            where
                user_to_id = v_user_to_id and
                level = i - 1
        ) then
            return;
        end if;

        return query
            insert into tmp
                select
                    i,
                    tmp.path || contact_currentstate.user_to_id,
                    contact_currentstate.user_from_id,
                    contact_currentstate.user_to_id
                from
                    contact_currentstate
                join
                    (select user_to_id, path from tmp where level = i - 1)
                tmp on
                    (contact_currentstate.user_from_id = tmp.user_to_id)
                where
                    contact_currentstate.user_to_id is not null and (
                        contact_currentstate.is_father or
                        contact_currentstate.is_mother
                    ) and
                    not exists (
                        select
                            1
                        from
                            tmp
                        where
                            contact_currentstate.user_from_id = tmp.user_from_id
                    )
        returning *; 
    end loop; 
end;

$$
    language plpgsql strict
"""

    print('\nRecreate postgresql functions and template tables for them')
    for op in ops.split("\n\f\n"):
        sql = op.strip()
        with connection.cursor() as cursor:
            cursor.execute(sql)


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0077_data_fix_null_trust_connections'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
