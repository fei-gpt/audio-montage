"""Structured output contract for Codex shot reviews."""
def obj(**properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def array(items):
    return {'type':'array','items':items}


def nullable(schema):
    return {'anyOf':[schema,{'type':'null'}]}


def dense_review_schema(template, timed):
    string={'type':'string'}
    number={'type':'number'}
    boolean={'type':'boolean'}
    strings=array(string)
    verdict={'type':'string','enum':['pass','conditional','fail','unknown','not_applicable']}
    observation=obj(value=string,evidence=string,unknowns=strings)
    dimensions=(template or {}).get('definition',{}).get('dimensions',[])
    visual=obj(actions=string,distinctive_features=strings,
               product_display=nullable(obj(light_state=string,light_change=string,product_motion=string,
                                            camera_motion=string,framing=string,uses=strings,
                                            limitations=strings,evidence=string)),
               light_sword=nullable(obj(packaging=string,visible_count=nullable({'type':'integer'}),
                                        arrangement=string,evidence=string,
                                        reveal=nullable(obj(status={'type':'string','enum':['present','absent','unknown']},
                                                            method={'type':'string','enum':['enter_frame','uncover','foreground_moves','packaging_first','other','unknown']},
                                                            evidence=string,start=nullable(number),end=nullable(number))))),
               product_observations=nullable(obj(**{d['id']:observation for d in dimensions})))
    properties=dict(visual_details=visual,facts=string,reason=string,
                    decision={'type':'string','enum':['keep','reject','uncertain']},
                    boundary_reviewed=boolean,start=nullable(number),end=nullable(number),
                    display_intent=string,duration_reason=string,
                    shot_review=nullable(obj(start=number,end=number,continuous=boolean,reviewed=boolean,method=string)),
                    use_conditions=strings,content_roles=strings,
                    assessment=obj(base=obj(content_legibility=verdict,temporal_integrity=verdict,
                                            technical_usability=verdict,evidence_sufficiency=verdict),
                                   user=array(obj(id=string,result=verdict,evidence=string))))
    if timed:
        properties['temporal_observation']=nullable(obj(
            kind={'type':'string','enum':['state','change']},purpose=string,unknowns=strings,
            points=array(obj(time=number,fact=string)),required_start=number,required_end=number))
    return obj(**properties)
