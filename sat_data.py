"""
Will fetch and store DISCOS data locally. Can fetch from databases:
'objects','launches','reentries','launch-sites','initial-orbits','fragmentations'

Usage example;
import sat_data
d = sat_data.get_data(database = 'objects')
"""

import requests
import numpy as np
import pandas as pd
import pickle as pkl
import json
import datetime as dt
import time
import glob
import re
import os
import io

esa_token = 'YourTokenHere'

class MyError(Exception):
    def __init___(self,args):
        Exception.__init__(self,"my exception was raised with arguments {0}".format(args))
        self.args = args

def get_data(database):
    """
    Check whether data exists in file and is recent.
    If so, read in. If not, retrieve from API and save.
    Return DataFrame
    """
    max_age_days = 365

    max_delta_t = dt.timedelta(days = max_age_days)
    
    now = dt.datetime.now().strftime('%Y-%m-%d')
    filelist = glob.glob(os.path.join('./esa_data',f'{database}_*'))

    # If no previous files exist, retrieve and write a new one
    if len(filelist) == 0:
        df = retrieve_discos_data(database)
        write_data(df = df, prefix = database)
    # Check if existing files are recent. If so, read 
    # in most recent, otherwise, retrieve and write new one.
    else:
        min_delta_t = dt.timedelta(days = max_age_days)
        for f in filelist:
            f_date = re.findall(r'\d{4}-\d{2}-\d{2}', f)
            if len(f_date) > 0:
                f_date = f_date[-1]
            else:
                continue
            f_date = dt.datetime.strptime(f_date,'%Y-%m-%d')
            delta_t = dt.datetime.now() - f_date
            if delta_t < min_delta_t:
                min_delta_t = delta_t
                recent_file = f
        if min_delta_t < max_delta_t:
            df = read_data(recent_file)
        else:
            df = retrieve_discos_data(database)
            write_data(df = df, prefix = database)
            
    return df

def write_data(df, prefix):
    """
    Write the data to file with appropriate date and prefix 
    """

    datestr = dt.datetime.now().strftime('%Y-%m-%d')
    output_file = f'./esa_data/{prefix}_{datestr}.csv'
        
    # Write the data
    df.to_csv(output_file, index = False)

    print(f'Data written to file {output_file}')

    return 

def read_data(filename):
    """
    Read data from csv file
    """

    df = pd.read_csv(filename)

    print(f'Read data from file {filename}')

    return df


def retrieve_discos_data(database):
    """
    """

    discos_url = 'https://discosweb.esoc.esa.int'
    db_url = f'{discos_url}/api/{database}'

    #TODO: Check for saved recent data and return if found

    print('No recent files found, attempting to retrieve data from')
    print(discos_url)
    print('...')

    discos_headers = {'Authorization': f'Bearer {esa_token}'} 
    params = discos_params(database)

    response = requests.get( 
       db_url, 
       headers=discos_headers, 
       params=params, 
    )    

    if not response.ok:
        raise MyError(response.json()['error'], "Discos request failed")

    dat = response.json()['data']
    df = pd.json_normalize(dat)
    last_page = response.json()['meta']['pagination']['totalPages'] 

    for page in range(2,last_page + 1):
        print(page, ' / ', last_page)
        params['page[number]'] = page
        response = requests.get( 
           db_url, 
           headers=discos_headers, 
           params=params, 
        )    
        resp_head = response.headers
        limit_remain = int(resp_head['X-Ratelimit-Remaining']) 
        if limit_remain == 0:
            wait_time = float(resp_head['Retry-After']) + 5
            print(f'Exceeded API request limit.') 
            print(f'Waiting {wait_time} seconds ...')
            time.sleep(float(wait_time))
            response = requests.get( 
               db_url, 
               headers=discos_headers, 
               params=params, 
            )    
             
        dat = response.json()['data']
        dfi = pd.json_normalize(dat)
        df = df.append(dfi, ignore_index = True)

    df = clean_discos(database = database, df = df)
    print('Data retrieved')

    #TODO Save/pickle data

    return df 

def clean_discos(database, df):
    clean = {
        'objects' : clean_discos_objects,
        'launches' : clean_discos_launches,
        'reentries' : clean_discos_reentries,
        'launch-sites' : clean_discos_launchsites,
        'initial-orbits' : clean_discos_orbits,
        'fragmentations': clean_discos_fragmentations,
        }
    
    return clean[database](df)

def clean_discos_objects(df):
    drop_cols = ['type',
                'relationships.states.links.self',           
                'relationships.states.links.related',             
                'relationships.initialOrbits.links.self',         
                'relationships.initialOrbits.links.related',      
                'relationships.launch.links.self',      
                'relationships.launch.links.related',               
                'relationships.launch.data.type',             
                'relationships.reentry.links.self',                 
                'relationships.reentry.links.related',              
                'relationships.reentry.data.type',            
                'relationships.operators.links.self',               
                'relationships.operators.links.related',            
                'relationships.destinationOrbits.links.self',       
                'relationships.destinationOrbits.links.related',    
                'relationships.reentry.data',  
                'relationships.launch.data',
                'links.self']

    rename_cols = {
                'id' : 'DiscosID',                  
                'attributes.cosparId' : 'IntlDes', 
                'attributes.xSectAvg' : 'XSectAvg', 
                'attributes.depth'    : 'Depth', 
                'attributes.xSectMin' : 'XSectMin',
                'attributes.vimpelId' : 'VimpelId',
                'attributes.shape'    : 'Shape',
                'attributes.satno'    : 'SatNo',
                'attributes.name'     : 'SatName',
                'attributes.height'   : 'Height',
                'attributes.objectClass' : 'ObjectType',
                'attributes.mass'        : 'Mass',
                'attributes.xSectMax'    : 'XSectMax',
                'attributes.length'      : 'Length',
                'relationships.initialOrbits.data' : 'InitOrbitId',
                'relationships.launch.data.id'     : 'LaunchId',
                'relationships.reentry.data.id'    : 'ReentryId',
                'relationships.operators.data'     : 'OperatorId',
                'relationships.destinationOrbits.data' : 'DestOrbitId',
                }

    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)

    df['InitOrbitId'] = df['InitOrbitId'].apply(lambda x: np.nan if not x else 
                                                (str(x[0]['id']) if len(x) == 1 else
                                                    [str(xi['id']) for xi in x]))

    df['DestOrbitId'] = df['DestOrbitId'].apply(lambda x: np.nan if not x else 
                                                (str(x[0]['id']) if len(x) == 1 else
                                                    [str(xi['id']) for xi in x]))

    df['OperatorId'] = df['OperatorId'].apply(lambda x: np.nan if not x else 
                                                (str(x[0]['id']) if len(x) == 1 else
                                                    [str(xi['id']) for xi in x]))

    df['VimpelId'] = df['VimpelId'].apply(lambda x: np.nan if x is None else str(x))

    return df

def clean_discos_launches(df):
    drop_cols = ['type',
                'relationships.site.links.self',    
                'relationships.site.links.related',    
                'relationships.site.data.type',
                'relationships.objects.links.self',    
                'relationships.objects.links.related', 
                'relationships.entities.links.self',
                'relationships.entities.links.related',
                'relationships.vehicle.links.self',
                'relationships.vehicle.links.related',
                'relationships.site.data',
                'links.self']

    rename_cols = {
                'id' : 'LaunchId',                  
                'relationships.site.data.id'    : 'LaunchSiteId',
                'attributes.epoch'              : 'Epoch',          
                'attributes.flightNo'           : 'FlightNo',        
                'attributes.failure'            : 'Failure',         
                'attributes.cosparLaunchNo'     : 'CosparLaunchNo', 
                }

    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)

    df['LaunchSiteId'] = df['LaunchSiteId'].apply(lambda x: np.nan if x is None else str(x))

    df['Epoch'] = pd.to_datetime(df['Epoch'])

    return df

def clean_discos_reentries(df):
    drop_cols = ['type',
                'relationships.objects.links.self',
                'relationships.objects.links.related',
                'links.self'] 

    rename_cols = {
                'id' : 'ReentryId',
                'attributes.epoch' : 'Epoch'
                }

    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)
    df['Epoch'] = pd.to_datetime(df['Epoch'])

    return df

def clean_discos_launchsites(df):
    drop_cols = ['type',
                'relationships.launches.links.self', 
                'relationships.launches.links.related',   
                'relationships.operators.links.self', 
                'relationships.operators.links.related', 
                'links.self',
                ]

    rename_cols = {
                'id'             : 'LaunchSiteId',
                'attributes.constraints'    : 'Constraints', 
                'attributes.pads'           : 'Pads',
                'attributes.altitude'       : 'Altitude',
                'attributes.latitude'       : 'Latitude',
                'attributes.azimuths'       : 'Azimuths',
                'attributes.name'           : 'Name',
                'attributes.longitude'      : 'Longitude'
                }

    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)

    return df

def clean_discos_orbits(df):
    drop_cols = ['type',
                'relationships.object.links.self', 
                'relationships.object.links.related', 
                'links.self',
                ]

    rename_cols = {
                'id'                : 'OrbitId',
                'attributes.sma'    : 'SemiMajorAxis',
                'attributes.epoch'  : 'Epoch',
                'attributes.aPer'   : 'ArgPeriapsis',
                'attributes.inc'    : 'Inclination',
                'attributes.mAno'   : 'MeanAnomoly',
                'attributes.ecc'    : 'Eccentricity',
                'attributes.raan'   : 'RAAN',
                'attributes.frame'  : 'RefFrame',
                }

    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)

    return df


def clean_discos_fragmentations(df):

    drop_cols = ['type',
                'relationships.objects.links.self',
                'relationships.objects.links.related', 
                'links.self',
                ]

    rename_cols = {
                'id'    :   'FragmentationId', 
                'attributes.eventType'          :   'eventType',
                'attributes.longitude'          :   'Longitude',
                'attributes.comment'            :   'Comment',
                'attributes.epoch'              :   'Epoch',  
                'attributes.latitude'           :   'Latitude',
                'attributes.altitude'           :   'Altitude',
                'relationships.objects.data'    :   'DiscosIds',
            }


    df.drop(columns = drop_cols, inplace = True)
    df.rename(columns = rename_cols, inplace = True)

    df['Epoch'] = pd.to_datetime(df['Epoch'])
    #df['DiscosIds'] = df['DiscosIds'].apply(lambda x : [xx['id'] for xx in json.loads(x.replace('\'','\"'))])
    df['DiscosIds'] = df['DiscosIds'].apply(lambda x : list(int(xx['id']) for xx in x))

    return df


def discos_params(database):

    if database == 'objects':
        discos_params = {
                'include' : 'launch,reentry,initialOrbits,destinationOrbits,operators',
                'page[number]' : 1, 
                'page[size]' : 100, 
                'sort': 'satno', 
                #'filter': "eq(satno,1)", 
                #'fields[object]':'cosparId,satno,name,launch,reentry', 
                #'fields[launch]':'epoch', 
                #'filter': "eq(objectClass,Payload)&gt(reentry.epoch,epoch:'2020-01-01')", 
                }
    elif database == 'launches':
        discos_params = {
                'include' : 'site',
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'launch-systems':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'launch-sites':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'initial-orbits':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'destination-orbits':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'fragmentation-event-types':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'fragmentations':
        discos_params = {
                'include' : 'objects',
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'reentries':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }
    elif database == 'entities':
        discos_params = {
                'page[number]' : 1, 
                'page[size]' : 100, 
                }

    return discos_params
        

def get_ucsdata():

    max_delta_t = dt.timedelta(days=365)

    now = dt.datetime.now()
    filelist = glob.glob(os.path.join('./esa_data','ucsdata_*'))

    if len(filelist) != 0:
        dates = [re.findall(r'\d{4}-\d{2}-\d{2}', f)[0] for f in filelist]
        dates = [dt.datetime.strptime(d,'%Y-%m-%d') for d in dates]
        delta_t = [now - d for d in dates]
        recent_i = int(np.argmin(delta_t))
        recent_file = filelist[recent_i]
        recent_date = dates[recent_i].strftime('%Y-%m-%d')

        print('UCS data file found, generated on {}'.format(recent_date))
        print('File: {}'.format(recent_file))
        print('')
        df = pd.read_csv(recent_file)
    else:
        print('No saved UCS data files found, generating new data ...')

        with requests.Session() as session:
            # run the session in a with block to force session to close if we exit

            # need to log in first. note that we get a 200 to say the web site got the data, not that we are logged in

            resp = session.get('https://www.ucsusa.org/media/11492')
            if resp.status_code != 200:
                print(resp)
                raise MyError(resp, "GET fail on request for Box Score")

            df = pd.read_excel(io.BytesIO(resp.content))

            print('Data retrieved')

            col_rename = {  'Name of Satellite, Alternate Names': 'SATNAME',
                            'Country of Operator/Owner': 'COUNTRY',
                            'Country/Org of UN Registry': 'COUNTRY_UN_REG',
                            'Operator/Owner': 'OWNER',
                            'Users': 'USERS',
                            'Purpose': 'PURPOSE',
                            'Detailed Purpose' : 'DETAILED_PURPOSE',
                            'Class of Orbit': 'ORBIT_CLASS',
                            'Type of Orbit': 'ORBIT_TYPE',
                            'Longitude of GEO (degrees)': 'LONGITUDE_GEO',
                            'Perigee (km)': 'PERIGEE',
                            'Apogee (km)': 'APOGEE',
                            'Eccentricity': 'ECCENTRICITY',
                            'Inclination (degrees)': 'INCLINATION',
                            'Period (minutes)': 'PERIOD',
                            'Launch Mass (kg.)': 'MASS_LAUNCH',
                            'Dry Mass (kg.)': 'MASS_DRY',
                            'Power (watts)': 'POWER',
                            'Date of Launch': 'LAUNCH',
                            'Expected Lifetime (yrs.)': 'EXP_LIFETIME',
                            'Contractor': 'CONTRACTOR',
                            'Country of Contractor': 'COUNTRY_CONTRACTOR',
                            'Launch Site': 'SITE',
                            'Launch Vehicle': 'LAUNCH_VEHICLE',
                            'COSPAR Number': 'INTLDES',
                            'NORAD Number': 'NORAD_CAT_ID',
                            'Comments': 'COMMENTS'
                        }

            df.rename(columns=col_rename, inplace=True)

            df.to_csv('./esa_data/ucsdata_' + now.strftime('%Y-%m-%d') + '.csv', index=False)

            print('Data saved to file.')

            session.close()

    #years = np.array([dt.datetime.strptime(d,'%Y-%m-%d').year for d in df.LAUNCH])
    #df['LAUNCH_YEAR'] = years
    df['LAUNCH'] = pd.to_datetime(df.LAUNCH)
    years = np.zeros((len(df)))
    df['LAUNCH_YEAR'] = df.LAUNCH.dt.year 



    return df
 


                
