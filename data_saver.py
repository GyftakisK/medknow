#!/usr/bin/python !/usr/bin/env python
# -*- coding: utf-8 -*


# Functions to extract knowledge from medical text. Everything related to 
# reading, parsing and extraction needed for the knowledge base. Also,
# some wrappers for SemRep, MetaMap and Reverb.

import json
import os
import py2neo
import time
import random
import re
import unicodecsv as csv2
import pymongo
from .config import settings
from .utilities import time_log
from .data_extractor import chunk_document_collection
from multiprocessing import cpu_count, Pool


def save_json2(json_):
    """
    Helper function to save enriched medical json to file.
    Input:
        - json_: dic,
        json-style dictionary generated from the extractors in the
        previous phase
    """

    # Output file location from settings
    outfile = settings['out']['json']['out_path']
    with open(outfile, 'w+') as f:
        json.dump(json_, f, indent=3)

def save_json(json_):
    """
    Helper function to save enriched medical json to file
.    Input:
        - json_: dic,
        json-style dictionary generated from the extractors in the
        previous phase
    """

    # Output file location from settings
    outfile = settings['out']['json']['out_path']
    if settings['pipeline']['in']['stream'] or settings['pipeline']['in']['parallel']:
        print('mpainei append')
        if os.path.isfile(outfile):
            with open(outfile, 'r') as f:
                docs1 = json.load(f)[settings['out']['json']['json_doc_field']]
            json_[settings['out']['json']['json_doc_field']] = json_[settings['out']['json']['json_doc_field']] + docs1
    with open(outfile, 'w+') as f:
        json.dump(json_, f, indent=3)

    # with open (outfile, mode="r+") as file:
    #     file.seek(0,2)
    #     position = file.tell() -1
    #     file.seek(position)
    #     file.write( ",{}]".format(json.dumps(dictionary)) )
    
    # with open(outfile, 'a+') as f:
    #     json1 = json.load(f)
        



def save_csv(json_):
    """
    Helper function to save enriched medical json to file.
    Input:
        - json_: dic,
        json-style dictionary generated from the extractors in the
        previous phase
    """

    # Output file location from settings
    outfile = settings['out']['json']['out_path']
    with open(outfile, 'w+') as f:
        json.dump(json_, f, indent=3)



def save_neo4j(json_):
    """
    Helper function to save enriched medical json to file.
    Input:
        - json_: dic,
        json-style dictionary generated from the extractors in the
        previous phase
    """

    # Output file location from settings
    outfile = settings['out']['json']['out_path']
    with open(outfile, 'w+') as f:
        json.dump(json_, f, indent=3)

def aggregate_mentions(entity_pmc_edges):
    """
    Function to aggregate recurring entity:MENTIONED_IN:pmc relations.
    Input:
        - entity_pmc_edges: list,
        list of dicts as generated by create_neo4j_ functions
    Outpu:
        - entity_pmc_edges: list,
        list of dicts with aggregated values in identical ages
    """
    uniques = {}
    c = 0
    for edge in entity_pmc_edges:
        cur_key = str(edge[':START_ID'])+'_'+str(edge[':END_ID'])
        flag = False
        if cur_key in uniques:
            uniques[cur_key]['score:float[]'] = uniques[cur_key]['score:float[]']+';'+edge['score:float[]']
            uniques[cur_key]['sent_id:string[]'] = uniques[cur_key]['sent_id:string[]']+';'+edge['sent_id:string[]']
            uniques[cur_key]['resource:string[]'] = uniques[cur_key]['resource:string[]']+';'+edge['resource:string[]']
            flag = True
        else:
            uniques[cur_key] = edge
        if flag:
            c += 1
    un_list = []
    time_log('Aggregated %d mentions from %d in total' % (c, len(entity_pmc_edges)))
    for k, v in uniques.items():
        un_list.append(v)
    return un_list


def aggregate_relations(relations_edges):
    """
    Function to aggregate recurring entity:SEMREP_RELATION:entity relations.
    Input:
        - relations_edges: list,
        list of dicts as generated by create_neo4j_ functions
    Outpu:
        - relations_edges: list,
        list of dicts with aggregated values in identical ages
    """
    uniques = {}
    c = 0
    for edge in relations_edges:
        cur_key = str(edge[':START_ID'])+'_'+str(edge[':TYPE'])+'_'+str(edge[':END_ID'])
        flag = False
        if cur_key in uniques:
            if 'sent_id:string[]' in list(edge.keys()):
                if edge['sent_id:string[]'] in uniques[cur_key]['sent_id:string[]']:
                    continue
            for field in list(edge.keys()):
                if not(field in [':START_ID', ':TYPE', ':END_ID']):
                    uniques[cur_key][field] = uniques[cur_key][field]+';'+edge[field]
            flag = True
        else:
            uniques[cur_key] = edge
        if flag:
            c += 1
    un_list = []
    time_log('Aggregated %d relations from %d in total' % (c, len(relations_edges)))
    for k, v in uniques.items():
        un_list.append(v)
    return un_list


def create_neo4j_results(json_, key='harvester'):
    """
    Helper function to call either the create_neo4j_harvester or the
    create_neo4j_edges function, according to the type of input.
    Input:
        - json_: dic,
        dictionary-json style generated from the parsers/extractors in the
        previous stages
        - key: str,
        string for denoting which create_neo4j_ function to use
    Output:
        - results: dic,
        json-style dictionary with keys 'nodes' and 'edges' containing
        a list of the transformed nodes and edges to be created/updated in
        neo4j. Each element in the list has a 'type' field denoting the type
        of the node/edge and the 'value' field containg the nodes/edges
    """
    if key == 'harvester':
        results = create_neo4j_harvester(json_)
    elif key == 'edges':
        results = create_neo4j_edges(json_)
    else:
        time_log('Type %s of data not yet supported!' % key)
        raise NotImplementedError
    return results

def create_neo4j_edges(json_):
    """
    Function that takes the edges file as provided and generates the nodes
    and relationships entities needed for creating/updating the neo4j database.
    Currently supporting: 
        - Nodes: ['Articles(PMC)', 'Entities(MetaMapConcepts)'] 
        - Edges: ['Relations between Entities']
    Input:
        - json_: dic,
        json-style dictionary generated from the parser in the
        previous phase
    Output:
        - results: dic,
        json-style dictionary with keys 'nodes' and 'edges' containing
        a list of the transformed nodes and edges to be created/updated in
        neo4j. Each element in the list has a 'type' field denoting the type
        of the node/edge and the 'value' field containg the nodes/edges
    """
    # docfield containing list of elements containing the relations
    edgefield = settings['load']['edges']['itemfield']
    # field containing the type of the node for the subject
    sub_type = settings['load']['edges']['sub_type']
    # field containing the source of the node for the subject
    sub_source = settings['load']['edges']['sub_source']
    # field containing the type of the node for the object
    obj_type = settings['load']['edges']['obj_type']
    # field containing the source of the node for the object
    obj_source = settings['load']['edges']['obj_source']
    results = {'nodes':[], 'edges':[{'type':'NEW', 'values':[]}]}
    entities_nodes = []
    articles_nodes = []
    other_nodes_sub = []
    other_nodes_obj = []

    for edge in json_[edgefield]:
        if sub_type == 'Entity':
            if not(edge['s'] in entities_nodes):
                entities_nodes.append(edge['s'])
        elif sub_type == 'Article':
            if not(edge['s'] in articles_nodes):
                articles_nodes.append(edge['s'])
        else:
            if not(edge['s'] in other_nodes_sub):
                other_nodes_sub.append(edge['s'])
        if obj_type == 'Entity':
            if not(edge['o'] in entities_nodes):
                entities_nodes.append(edge['o'])
        elif obj_type == 'Article':
            if not(edge['o'] in articles_nodes):
                articles_nodes.append(edge['o'])
        else:
            if not(edge['o'] in other_nodes_obj):
                other_nodes_obj.append(edge['o'])
        #sub_id_key = next((key for key in edge['s'].keys() if ':ID' in key), None)
        #obj_id_key = next((key for key in edge['o'].keys() if ':ID' in key), None)
        results['edges'][0]['values'].append({':START_ID':edge['s']['id:ID'], ':TYPE':edge['p'], 'resource:string[]':settings['neo4j']['resource'], ':END_ID':edge['o']['id:ID']})
    if entities_nodes:
        results['nodes'].append({'type': 'Entity', 'values': entities_nodes})
    if articles_nodes:
        results['nodes'].append({'type': 'Article', 'values': articles_nodes})
    if other_nodes_sub:
        results['nodes'].append({'type': sub_type, 'values': other_nodes_sub})
    if other_nodes_obj:
        results['nodes'].append({'type': obj_type, 'values': other_nodes_obj})
    return results

def create_neo4j_harvester(json_):
    """
    Function that takes the enriched json_ file and generates the nodes
    and relationships entities needed for creating/updating the neo4j database.
    Currently supporting: 
        - Nodes: ['Articles(PMC)', 'Entities(UMLS-Concepts)'] 
        - Edges: ['Relations between Entities', 'Entity:MENTIONED_IN:Article']
    Input:
        - json_: dic,
        json-style dictionary generated from the extractors in the
        previous phase
    Output:
        - results: dic,
        json-style dictionary with keys 'nodes' and 'edges' containing
        a list of the transformed nodes and edges to be created/updated in
        neo4j. Each element in the list has a 'type' field denoting the type
        of the node/edge and the 'value' field containg the nodes/edges
    """
    # docfield containing list of elements
    out_outfield = settings['out']['json']['itemfield']
    # textfield to read text from
    out_textfield = settings['out']['json']['json_text_field']
    # idfield where id of document is stored
    out_idfield = settings['out']['json']['json_id_field']
    # labelfield where the label is located
    out_labelfield = settings['out']['json']['json_label_field']
    # Sentence Prefix
    sent_prefix = settings['load']['text']['sent_prefix']
    if sent_prefix == 'None' or not(sent_prefix):
        sent_prefix = ''
    entities_nodes = []
    unique_sent = {}
    articles_nodes = []
    entity_pmc_edges = []
    relations_edges = []
    unique_cuis = []
    for doc in json_[out_outfield]:
        pmid = doc[out_idfield]
        for sent in doc['sents']:
            cur_sent_id = str(pmid)+'_' + str(sent_prefix) + '_' +  str(sent['sent_id'])
            unique_sent[cur_sent_id] = sent['sent_text']
            for ent in sent['entities']:
                if ent['cuid']:
                    if not(ent['cuid'] in unique_cuis):
                        unique_cuis.append(ent['cuid'])
                        if (type(ent['sem_types']) == list and len(ent['sem_types']) > 1):
                            sem_types = ';'.join(ent['sem_types'])
                        elif (',' in ent['sem_types']):
                            sem_types = ';'.join(ent['sem_types'].split(','))
                        else:
                            sem_types = ent['sem_types']
                        #if not(ent['cuid']):
                        entities_nodes.append({'id:ID': ent['cuid'], 
                                         'label': ent['label'], 
                                         'sem_types:string[]': sem_types})
                    entity_pmc_edges.append({':START_ID': ent['cuid'],
                                             'score:float[]': ent['score'],
                                             'sent_id:string[]': cur_sent_id,
                                             ':TYPE':'MENTIONED_IN',
                                             'resource:string[]':settings['neo4j']['resource'],
                                             ':END_ID': pmid})
            for rel in sent['relations']:
                if rel['subject__cui'] and rel['object__cui']:
                    relations_edges.append({':START_ID': rel['subject__cui'],
                                     'subject_score:float[]': rel['subject__score'],
                                     'subject_sem_type:string[]': rel['subject__sem_type'],
                                     ':TYPE': re.sub(r'\(.*\)', '', rel['predicate']),
                                     'pred_type:string[]': rel['predicate__type'],
                                     'object_score:float[]': rel['object__score'],
                                     'object_sem_type:string[]': rel['object__sem_type'],
                                     'sent_id:string[]': cur_sent_id,
                                     'negation:string[]': rel['negation'],
                                     'resource:string[]':settings['neo4j']['resource'],
                                     ':END_ID': rel['object__cui']})            
        articles_nodes.append({'id:ID': doc[out_idfield], 
                               'title': doc[out_labelfield], 
                               'journal': doc['journal']})
    entity_pmc_edges = aggregate_mentions(entity_pmc_edges)
    relations_edges = aggregate_relations(relations_edges)
    results = {'nodes': [{'type': 'Entity', 'values': entities_nodes}, {'type': 'Article', 'values': articles_nodes}],
               'edges': [{'type': 'relation', 'values': relations_edges}, {'type': 'mention', 'values': entity_pmc_edges}]
               }
    return results


def create_neo4j_csv(results):
    """
    Create csv's for use by the neo4j import tool. Relies on create_neo4j_ functions
    output and transforms it to suitable format for automatic importing.
    Input: 
        - results: dic,
        json-style dictionary. Check create_neo4j_ function output for
        details
    Output:
        - None just saves the documents in the allocated path as defined
        in settings.yaml 
    """
    outpath = settings['out']['csv']['out_path']
    entities_nodes = None
    articles_nodes = None
    relations_edges = None
    entity_pmc_edges = None
    other_nodes = []
    other_edges = []
    for nodes in results['nodes']:
        if nodes['type'] == 'Entity':
            entities_nodes = nodes['values']
        elif nodes['type'] == 'Article':
            articles_nodes = nodes['values']
        else:
            other_nodes.extend(nodes['values'])
    for edges in results['edges']:
        if edges['type'] == 'relation':
            relations_edges = edges['values']
        elif edges['type'] == 'mention':
            entity_pmc_edges = edges['values']
        elif edges['type'] == 'NEW':
            other_edges.extend(edges['values'])

    dic_ = {
        'entities.csv': entities_nodes,
        'articles.csv': articles_nodes,
        'other_nodes.csv': other_nodes,
        'entities_pmc.csv':entity_pmc_edges, 
        'relations.csv':relations_edges,
        'other_edges.csv': other_edges
    }

    dic_fiels = {
        'entities.csv': ['id:ID', 'label', 'sem_types:string[]'],
        'articles.csv': ['id:ID', 'title', 'journal','sent_id:string[]'],
        'other_nodes.csv': ['id:ID'],
        'entities_pmc.csv':[':START_ID','score:float[]','sent_id:string[]', 'resource:string[]', ':END_ID'], 
        'relations.csv':[':START_ID','subject_score:float[]','subject_sem_type:string[]',':TYPE','pred_type:string[]', 
        'object_score:float[]','object_sem_type:string[]','sent_id:string[]','negation:string[]', 'resource:string[]', ':END_ID'],
        'other_edges.csv':[':START_ID', ':TYPE', 'resource:string[]', ':END_ID']
    }

    for k, toCSV in dic_.items():
        if toCSV:
            keys = list(toCSV[0].keys())
            out = os.path.join(outpath, k)
            with open(out, 'wb') as output_file:
                time_log("Created file %s" % k)
                dict_writer = csv2.DictWriter(output_file, fieldnames=dic_fiels[k], encoding='utf-8')
                dict_writer.writeheader()
                dict_writer.writerows(toCSV)
    time_log('Created all documents needed')



def fix_on_create_nodes(node):
    """
    Helper function to create the correct cypher string for
    querying and merging a new node to the graph. This is used
    when no node is matched and a new one has to be created.
    Input:
        - node: dic,
        dictionary of a node generated from some create_neo4j_
        function
    Output:
        - s: string,
        part of cypher query, responsible handling the creation of anew node
    """
    s = ' '
    # Has at least one other attribute to create than id
    if len(list(node.keys()))>1:
        s = 'ON CREATE SET '
        for key, value in node.items():
            if (value) and (value != " "):
                if 'ID' in key.split(':'):
                    continue
                elif 'string[]' in key:
                    field = key.split(':')[0]
                    string_value = '['
                    for i in value.split(';'):
                        string_value += '"' + i + '"' + ','
                    string_value = string_value[:-1] + ']'
                    s += ' a.%s = %s,' % (field, string_value)
                elif 'float[]' in key:
                    field = key.split(':')[0]
                    string_value = str([int(i) for i in value.split(';')])
                    s += ' a.%s = %s,' % (field, string_value)
                else:
                    field = key.split(':')[0]
                    s += ' a.%s = "%s",' % (field, value.replace('"', "'"))
        s = s[:-1]
    # No attributes
    return s


def create_merge_query(node, type_):
    """
    Creating the whole merge and update cypher query for a node.
    Input:
        - node: dic,
        dictionary of a node containing the attributes of the
        node
        - type_: str,
        type of the node to be merged
    Output:
        - quer: str,
        the complete cypher query ready to be run
    """
    quer = """
    MERGE (a:%s {id:"%s"})
    %s""" % (type_, node["id:ID"], fix_on_create_nodes(node))
    return quer


def populate_nodes(graph, nodes, type_):
    """
    Function that actually calls the cypher query and populates the graph
    with nodes of type_, merging on already existing nodes on their id_.
    Input:
        -graph: py2neo.Graph,
        object representing the graph in neo4j. Using py2neo.
        - nodes: list,
        list of dics containing the attributes of each node
        - type_: str,
        type of the node to be merged
    Output: None, populates the db.
    """
    c = 0
    total_rel = 0
    time_log('~~~~~~  Will create nodes of type: %s  ~~~~~~' % type_)
    for ent in nodes:
        c += 1
        quer = create_merge_query(ent, type_)
        f = graph.run(quer)
        total_rel += f.stats()['nodes_created']
        if c % 1000 == 0 and c > 999:
            time_log("Process: %d -- %0.2f %%" % (c, 100*c/float(len(nodes))))
    time_log('#%s : %d' % (type_, c))
    time_log('Finally added %d new nodes!' % total_rel) 


def create_edge_query(edge, sub_ent=settings['load']['edges']['sub_type'], 
                       obj_ent=settings['load']['edges']['obj_type']):
    """
    Takes as input an edge, in the form of a dictionary, and returns the
    corresponding cypher query that:
    1) First Matches the start-end nodes and the type of the edge
    2) Merges the edge the following way:
        - If the edge doesn't exist it creates it setting all attributes
          of the edge according to its' values
        - If the edge exists, it updates the attributes that are both in the
          graph edge and the dictionary and creates the attributes that are not
          found in the graph edge but are provided in the edge dictionary
    Input:
        - edge, dict
        dictionary containing the edge properties
        - sub_ent, str
        string denoting what type is the subject node
        - obj_ent, str
        string denoting what type is the object node
    Output:
        - s, string
        query string to perform
    """
    s = """MATCH (a:%s {id:"%s"}), (b:%s {id:"%s"}) 
           MERGE (a)-[r:%s]->(b)
           ON MATCH SET """ % (sub_ent, edge[':START_ID'], obj_ent, edge[':END_ID'],  edge[':TYPE'])
    for key, value in edge.items():
        # Don't see why this check should be here???
        # if (value):
        if not(('START_ID' in key.split(':')) or ('END_ID' in key.split(':')) or ('TYPE' in key.split(':'))):
            if 'string[]' in key:
                field = key.split(':')[0]
                string_value = '['
                for i in value.split(';'):
                    string_value += '"' + i + '"' + ','
                string_value = string_value[:-1] + ']'
            elif 'float[]' in key:
                field = key.split(':')[0]
                # Dealing with empty or non-scored elements
                tmp_s = []
                for i in value.split(';'):
                    try:
                        tmp_s.append(int(i))
                    except ValueError:
                        tmp_s.append(0)
                string_value = str(tmp_s)
            else:
                field = key.split(':')[0]
                string_value = value.replace('"', "'")
            s += ' r.%s = CASE WHEN NOT EXISTS(r.%s) THEN %s ELSE r.%s + %s END,' % (field, field, string_value, field, string_value)
    s = s[:-1]
    s += ' ON CREATE SET '
    for key, value in edge.items():
        # Don't see why this check should be here???
        # if (value):
        if not(('START_ID' in key.split(':')) or ('END_ID' in key.split(':')) or ('TYPE' in key.split(':'))):
            if 'string[]' in key:
                field = key.split(':')[0]
                string_value = '['
                for i in value.split(';'):
                    string_value += '"' + i + '"' + ','
                string_value = string_value[:-1] + ']'
            elif 'float[]' in key:
                field = key.split(':')[0]
                # Dealing with empty or non-scored elements
                tmp_s = []
                for i in value.split(';'):
                    try:
                        tmp_s.append(int(i))
                    except ValueError:
                        tmp_s.append(0)
                string_value = str(tmp_s)
            else:
                field = key.split(':')[0]
                string_value = value.replace('"', "'")
            s += ' r.%s = %s,' % (field, string_value)
    s = s[:-1]
    return s




def populate_relation_edges(graph, relations_edges):
    """
    Function to create/merge the relation edges between existing entities.
    Input:
        - graph: py2neo.Graph,
        object representing the graph in neo4j. Using py2neo.
        - relations_edges: list,
        list of dics containing the attributes of each relation
    Output: None, populates the db.
    """
    c = 0
    total_rel = 0
    for edge in relations_edges:
        c += 1  
        quer = """
        Match (a:Entity {id:"%s"}), (b:Entity {id:"%s"})
        MATCH (a)-[r:%s]->(b)
        WHERE "%s" in r.sent_id
        Return r;
        """ % (edge[':START_ID'], edge[':END_ID'], edge[':TYPE'], edge['sent_id:string[]'].split(';')[0])
        f = graph.run(quer)
        if not f.forward() and edge[':START_ID'] and edge[':END_ID']:
            quer = create_edge_query(edge, 'Entity', 'Entity')
            # subj_s = '['
            # for i in edge['subject_sem_type:string[]'].split(';'):
            #     subj_s += '"' + i + '"' + ','
            # subj_s = subj_s[:-1] + ']'
            # obj_s = '['
            # for i in edge['object_sem_type:string[]'].split(';'):
            #     obj_s += '"' + i + '"' + ','
            # obj_s = obj_s[:-1] + ']'
            # sent_s = '['
            # for i in edge['sent_id:string[]'].split(';'):
            #     sent_s += '"' + i + '"' + ','
            # sent_s = sent_s[:-1] + ']'
            # neg_s = '['
            # for i in edge['negation:string[]'].split(';'):
            #     neg_s += '"' + i + '"' + ','
            # neg_s = neg_s[:-1] + ']'
            # sent_res = '['
            # for i in edge['resource:string[]'].split(';'):
            #     sent_res += '"' + i + '"' + ','
            # sent_res = sent_res[:-1] + ']'
            # quer = """
            # Match (a:Entity {id:"%s"}), (b:Entity {id:"%s"})
            # MERGE (a)-[r:%s]->(b)
            # ON MATCH SET r.subject_score = r.subject_score + %s, r.subject_sem_type = r.subject_sem_type + %s,
            # r.object_score = r.object_score + %s, r.object_sem_type = r.object_sem_type + %s,
            # r.sent_id = r.sent_id + %s, r.negation = r.negation + %s, r.resource = r.resource + %s
            # ON CREATE SET r.subject_score = %s, r.subject_sem_type =  %s,
            # r.object_score =  %s, r.object_sem_type =  %s,
            # r.sent_id =  %s, r.negation =  %s, r.resource = %s
            # """ % (edge[':START_ID'], edge[':END_ID'], edge[':TYPE'], 
            #        str([int(i) for i in edge['subject_score:float[]'].split(';')]), subj_s, 
            #        str([int(i) for i in edge['object_score:float[]'].split(';')]), obj_s,
            #      sent_s, neg_s, sent_res, str([int(i) for i in edge['subject_score:float[]'].split(';')]), subj_s, 
            #        str([int(i) for i in edge['object_score:float[]'].split(';')]), obj_s,
            #      sent_s, neg_s, sent_res)
            # print quer
            # print '~'*50
            # print edge
            # quer = """
            # Match (a:Entity {id:"%s"}), (b:Entity {id:"%s"})
            # MERGE (a)-[r:%s]->(b)
            # ON MATCH SET r.object_score = CASE WHEN NOT EXISTS(r.object_score) THEN %s ELSE r.object_score + %s END
            # """ % (edge[':START_ID'], edge[':END_ID'], edge[':TYPE'], 
            #        str([int(i) for i in edge['object_score:float[]'].split(';')]), str([int(i) for i in edge['object_score:float[]'].split(';')]))
            f = graph.run(quer)
            total_rel += f.stats()['relationships_created']
        if c % 1000 == 0 and c > 999:
            time_log('Process: %d -- %0.2f %%' % (c, 100*c/float(len(relations_edges))))
    time_log('#Relations :%d' % c)
    time_log('Finally added %d new relations!' % total_rel)

def populate_mentioned_edges(graph, entity_pmc_edges):
    """
    Function to create/merge the relation edges between existing entities.
    Input:
        - graph: py2neo.Graph,
        object representing the graph in neo4j. Using py2neo.
        - entity_pmc_edges: list,
        list of dics containing the attributes of each relation
    Output: None, populates the db.
    """

    c = 0
    total_rel = 0
    for edge in entity_pmc_edges:
        c += 1
        quer = """
        Match (a:Entity {id:"%s"}), (b:Article {id:"%s"})
        MATCH (a)-[r:%s]->(b)
        WHERE "%s" in r.sent_id
        Return r;
        """ % (edge[':START_ID'], edge[':END_ID'], edge[':TYPE'] , edge['sent_id:string[]'])
        f = graph.run(quer)
        if not f.forward() and edge[':START_ID'] and edge[':END_ID']:
            quer = create_edge_query(edge, 'Entity', 'Article')
            # sent_s = '['
            # for i in edge['sent_id:string[]'].split(';'):
            #     sent_s += '"' + i + '"' + ','
            # sent_s = sent_s[:-1] + ']'
            # sent_res = '['
            # for i in edge['resource:string[]'].split(';'):
            #     sent_res += '"' + i + '"' + ','
            # sent_res = sent_res[:-1] + ']'
            # quer = """
            # Match (a:Entity {id:"%s"}), (b:Article {id:"%s"})
            # MERGE (a)-[r:MENTIONED_IN]->(b)
            # ON MATCH SET r.score = r.score + %s, r.sent_id = r.sent_id + %s, r.resource = r.resource + %s
            # ON CREATE SET r.score = %s, r.sent_id = %s, r.resource = %s
            # """ % (edge[':START_ID'], edge[':END_ID'], 
            #        str([int(i) for i in edge['score:float[]'].split(';')]), sent_s, sent_res,
            #        str([int(i) for i in edge['score:float[]'].split(';')]), sent_s, sent_res)
            f = graph.run(quer)
            total_rel += f.stats()['relationships_created']
        if c % 1000 == 0 and c>999:
            time_log("Process: %d -- %0.2f %%" % (c, 100*c/float(len(entity_pmc_edges))))
    time_log('#Mentions: %d' % c)
    time_log('Finally added %d new mentions!' % total_rel)


def populate_new_edges(graph, new_edges):
    """
    Function to create/merge an unknwon type of edge.
    Input:
        - graph: py2neo.Graph,
        object representing the graph in neo4j. Using py2neo.
        - new_edges: list,
        list of dics containing the attributes of each relation
    Output: None, populates the db.
    """

    c = 0
    total_rel = 0
    # field containing the type of the node for the subject
    sub_type = settings['load']['edges']['sub_type']
    # field containing the type of the node for the object
    obj_type = settings['load']['edges']['obj_type']
    for edge in new_edges:
        c += 1  
        quer = """
        Match (a:%s {id:"%s"}), (b:%s {id:"%s"})
        MATCH (a)-[r:%s]->(b)
        WHERE ("%s" in r.resource)
        Return r;
        """ % (sub_type, edge[':START_ID'], obj_type, edge[':END_ID'], edge[':TYPE'], settings['neo4j']['resource'])
        f = graph.run(quer)
        if not f.forward() and edge[':START_ID'] and edge[':END_ID']:
            quer = create_edge_query(edge, sub_type, obj_type)
            # sent_res = '['
            # for i in edge['resource:string[]'].split(';'):
            #     sent_res += '"' + i + '"' + ','
            # sent_res = sent_res[:-1] + ']'
            # quer = """
            # MATCH (a:%s {id:"%s"}), (b:%s {id:"%s"})
            # MERGE (a)-[r:%s]->(b)
            # ON MATCH SET r.resource = r.resource + %s
            # ON CREATE SET r.resource = %s
            # """ % (sub_type, edge[':START_ID'], obj_type, edge[':END_ID'], 
            #        edge[':TYPE'], sent_res, sent_res)
            # print quer
            f = graph.run(quer)
            total_rel += f.stats()['relationships_created']
        if c % 1000 == 0 and c > 999:
            time_log("Process: %d -- %0.2f %%" % (c, 100*c/float(len(new_edges))))
    time_log('#Edges: %d' % c)
    time_log('Finally added %d new edges!' % total_rel)


def update_neo4j_parallel(results):
    
    """
    Function to create/update a neo4j database according to the nodeg and edges
    generated by the create_neo4j_ functions. Change settings.yaml values in
    the neo4j group of variables to match your needs.
    Input:
        - results: 
        json-style dictionary. Check create_neo4j_ functions output for
        details
    Output: None, creates/merges the nodes to the wanted database
    """
    found = False
    for key in ['nodes', 'edges']:
        for item in results[key]:
            if item['values'] and item['type'] == 'Entity':
                found = True
                break
        if found:
            break
    if not(found):
        time_log('NO NODES/EDGES FOUND! MOVING ON!')
        return 1
        #c = raw_input()
        #if c=='q':
        #    exit()
        #else:
        #    return
    try:
        N_THREADS = int(settings['num_cores'])
    except:
        N_THREADS = cpu_count()
    # results = {'nodes': [{'type': 'Entity', 'values': entities_nodes}, {'type': 'Article', 'values': articles_nodes}],
    #            'edges': [{'type': 'relation', 'values': relations_edges}, {'type': 'mention', 'values': entity_pmc_edges}]
    #            }
    par_res = [{'nodes': [{} for j in results['nodes']], 'edges': [{} for j in results['edges']]} for i in range(N_THREADS)]
    # Create mini batches of the results
    for i, nodes in enumerate(results['nodes']):
        par_nodes = chunk_document_collection(nodes['values'], N_THREADS)
        for batch_num in range(N_THREADS):
            par_res[batch_num]['nodes'][i]['type'] = nodes['type']
            par_res[batch_num]['nodes'][i]['values'] = par_nodes[batch_num]
    for i, edges in enumerate(results['edges']):
        par_edges = chunk_document_collection(edges['values'], N_THREADS)
        for batch_num in range(N_THREADS):
            par_res[batch_num]['edges'][i]['type'] = edges['type']
            par_res[batch_num]['edges'][i]['values'] = par_edges[batch_num]
    len_col = " | ".join([str(len(b)) for b in par_edges])
    time_log('Will break the collection into batches of: %s  %s edges!' % (len_col, edges['type']))
    pool = Pool(N_THREADS, maxtasksperchild=1)
    res = pool.map(update_neo4j_parallel_worker, par_res)
    pool.close()
    pool.join()
    del pool
    if sum(res) == N_THREADS:
        time_log('Completed parallel update of Neo4j!')
    else:
        time_log('Something wrong with the parallel execution?')
        time_log('Returned %d instead of %d' % (sum(res), N_THREADS))
    return 1

def update_neo4j_parallel_worker(results):
    """
    Just a worker interface for the different Neo4j update
    executions.
    Input:
        - results: 
        json-style dictionary. Check create_neo4j_ functions output for
        details
    Output:
        - res : dic,
        Output: None, creates/merges the nodes to the wanted database
    """
    # Update Neo4j as usual
    from pprint import pprint
    #pprint(results)
    #print('~'*50)
    try:
        time.sleep(random.randint(0, 10))
        update_neo4j(results)
    except Exception as e:
        time_log(e)
        return 0
    # Return 1 for everything is ok
    return 1


def update_neo4j(results):
    
    """
    Function to create/update a neo4j database according to the nodeg and edges
    generated by the create_neo4j_ functions. Change settings.yaml values in
    the neo4j group of variables to match your needs.
    Input:
        - results: 
        json-style dictionary. Check create_neo4j_ functions output for
        details
    Output: None, creates/merges the nodes to the wanted database
    """
    host = settings['neo4j']['host']
    port = settings['neo4j']['port']
    user = settings['neo4j']['user']
    password = settings['neo4j']['password']
    graph = py2neo.Graph(scheme='http', host=host, http_port=int(port), user=user, password=password)
    for nodes in results['nodes']:
        populate_nodes(graph, nodes['values'], nodes['type'])
    for edges in results['edges']:
        if edges['type'] == 'relation':
            time_log('~~~~~~  Will create Relations Between Entities ~~~~~~')
            populate_relation_edges(graph, edges['values'])
        elif edges['type'] == 'mention':
            time_log('~~~~~~  Will create Mentioned In  ~~~~~~')
            populate_mentioned_edges(graph, edges['values'])
        elif edges['type'] == 'NEW':
            time_log('~~~~~~  Will create new-type of edges~~~~~~')
            populate_new_edges(graph, edges['values'])
        else:
            time_log('Specific node type not handled! You have to update the code!')
            raise NotImplementedError 


def update_mongo_sentences(json_):
    """
    Helper function to save the sentences found in the enriched articles in
    mongodb. Connecting to a collection according to settings and then
    creating/updating the articles with the sentences found in them.
    Input:
        - json_: dic,
        json-style dictionary generated from the semrep extractor in the
        previous phase. Must make sure that there is a field named as indicated
        in json_['out']['json']['json_doc_field'], where the documents/articles
        are stored and each document/article has a field sents, as expected
        in the output of the semrep extractor.
    Output:
        None, just populates the database

    """
    uri = settings['mongo_sentences']['uri']
    db_name = settings['mongo_sentences']['db']
    collection_name = settings['mongo_sentences']['collection']
    client = pymongo.MongoClient(uri)
    db = client[db_name]
    collection = db[collection_name]
    new = 0
    upd = 0
    docs = json_[settings['out']['json']['itemfield']]
    for i, doc in enumerate(docs):
        try:
            cursor = collection.find({'id': doc['id']})
        except KeyError:
            cursor = None
        sents = [{'sent_id': sent['sent_id'], 'text': sent['sent_text']} for sent in doc['sents']]
        if not cursor or cursor.count() == 0:
            collection.insert_one({'id': doc['id'], 'sentences': sents})
            new += 1
        else:
            for mongo_doc in cursor:
                cur_sent = mongo_doc['sentences']
                cur_ids = [s['sent_id'] for s in cur_sent]
                new_sent = [s for s in sents if not(s['sent_id'] in cur_ids)]
                if new_sent:
                    cur_sent.extend(new_sent)
                    mongo_doc['sentences'] = cur_sent
                    collection.replace_one({'id': doc['id']}, mongo_doc)
                    upd += 1
        if i % 100 == 0 and i > 99:
            time_log("Process: %d -- %0.2f %%" % (i, 100*i/float(len(docs))))
    client.close()
    time_log('Finally updated %d -- inserted %d documents!' % (upd, new))



def save_mongo(json_):
    """
    Helper function to save edges/documents to mongo.
    Input:
        - json_: dic,
        json-style dictionary generated from the transformation modules in the
        previous phase. Must make sure that there is a field named as indicated
        in settings['out']['json']['json_doc_field'], where the edges/docs
        are stored. Specifically for the articles, they are replaced if another
        item with the same id is found in the collection.
    Output:
        None, just populates the database

    """
    uri = settings['out']['mongo']['uri']
    db_name = settings['out']['mongo']['db']
    collection_name = settings['out']['mongo']['collection']
    client = pymongo.MongoClient(uri)
    db = client[db_name]
    collection = db[collection_name]
    # Output Idfield
    idfield = settings['out']['json']['json_id_field']
    docs = json_[settings['out']['json']['itemfield']]
    for i, doc in enumerate(docs):
        if idfield in doc:
            result = collection.replace_one({'id': str(doc[idfield])}, doc, True)
        elif 'p' in doc:
            result = collection.insert_one(doc)
        else:
            time_log('Unknown type to persist to mongo')
            raise NotImplementedError
        if i % 100 == 0 and i > 99:
            time_log("Process: %d -- %0.2f %%" % (i, 100*i/float(len(docs))))
    client.close()
    return 1
