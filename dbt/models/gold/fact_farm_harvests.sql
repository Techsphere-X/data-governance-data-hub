-- Harvest quantities connected to farms, fields, and crops for production analysis.
select
    h.harvest_id,
    h.harvest_date,
    h.quantity_kg,
    h.quality_grade,
    f.field_id,
    f.field_name,
    f.soil_type,
    f.area_hectares as field_area_hectares,
    farm.farm_id,
    farm.farm_name,
    farm.location as farm_location,
    c.crop_id,
    c.crop_name,
    c.crop_type,
    c.growing_days,
    h.created_at

from {{ ref('stg_farm_harvests') }} h
left join {{ ref('stg_farm_fields') }} f
    on h.field_id = f.field_id
left join {{ ref('stg_farm_farms') }} farm
    on f.farm_id = farm.farm_id
left join {{ ref('stg_farm_crops') }} c
    on h.crop_id = c.crop_id