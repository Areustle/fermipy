
import re

import defaults 
from fermipy.utils import *
import fermipy
from fermipy.logger import Logger
from fermipy.logger import logLevel as ll

import xml.etree.cElementTree as ElementTree
from astropy import units as u
from astropy.coordinates import SkyCoord
import astropy.io.fits as pyfits

def xyz_to_lonlat(*args):

    if len(args) == 1:
        x, y, z = args[0][0],args[0][1],args[0][2]
    else:
        x, y, z = args[0], args[1], args[2]
        
    lat = np.pi/2. - np.arctan2(np.sqrt(x**2+y**2),z)
    lon = np.arctan2(y,x)
    return lon,lat
    
def lonlat_to_xyz(lon,lat):
    
    phi = lon
    theta = np.pi/2.-lat
    return np.array([np.sin(theta)*np.cos(phi),
                     np.sin(theta)*np.sin(phi),
                     np.cos(theta)])

def project(lon0,lat0,lon1,lat1):
    """This function performs a stereographic projection on the unit
    vector (lon1,lat1) with the pole defined at the reference unit
    vector (lon0,lat0)."""

    costh = np.cos(np.pi/2.-lat0)
    cosphi = np.cos(lon0)

    sinth = np.sin(np.pi/2.-lat0)
    sinphi = np.sin(lon0)

    xyz = lonlat_to_xyz(lon1,lat1)
    x1 = xyz[0]; y1 = xyz[1]; z1 = xyz[2]
    
    x1p = x1*costh*cosphi + y1*costh*sinphi - z1*sinth
    y1p = -x1*sinphi + y1*cosphi
    z1p = x1*sinth*cosphi + y1*sinth*sinphi + z1*costh
    
    r = np.arctan2(np.sqrt(x1p**2+y1p**2),z1p)
    phi = np.arctan2(y1p,x1p)

    return r*np.cos(phi), r*np.sin(phi)


def scale_parameter(p):
    
    if isinstance(p,str): p = float(p)
    
    if p > 0:    
        scale = 10**-np.round(np.log10(1./p))
        return p/scale, scale
    else:
        return p, 1.0


spectrum_type_pars = {
    'PowerLaw' : ['Prefactor','Index','Scale'],
    'PowerLaw2' : ['Integral','Index','LowerLimit','UpperLimit'],
    'ConstantValue' : ['Value'],
    'BrokenPowerLaw' : ['Prefactor','Index1','Index2'],    
    'LogParabola' : ['norm','alpha','beta','Eb'],
    'PLSuperExpCutoff' : ['Prefactor','Index1','Index2','Cutoff','Scale'],
    'ExpCutoff' : ['Prefactor','Index1','Cutoff'],
    'FileFunction' : ['Normalization'],
    }
    
    
default_par_dict = {
    'Prefactor' :
        {'name' : 'Prefactor', 'value' : 1.0, 'scale' : None, 'min' : 0.01, 'max' : 100.0, 'free' : '0'},
    'norm' :
        {'name' : 'norm', 'value' : 1.0, 'scale' : None, 'min' : 0.01, 'max' : 100.0, 'free' : '0'},
    'Scale' :
        {'name' : 'Scale', 'value' : 1000.0, 'scale' : 1.0, 'min' : 1.0, 'max' : 1.0, 'free' : '0'},
    'Eb' :
        {'name' : 'Eb', 'value' : 1.0, 'scale' : None, 'min' : 0.01, 'max' : 10.0, 'free' : '0'},
    'Cutoff' :
        {'name' : 'Cutoff', 'value' : 1.0, 'scale' : None, 'min' : 0.01, 'max' : 10.0, 'free' : '0'},
    'Index' :
        {'name' : 'Index', 'value' : 2.0, 'scale' : -1.0, 'min' : 0.0, 'max' : 5.0, 'free' : '0'},
    'alpha' :
        {'name' : 'alpha', 'value' : 0.0, 'scale' : 1.0, 'min' : -5.0, 'max' : 5.0, 'free' : '0'},
    'beta' :
        {'name' : 'beta', 'value' : 0.0, 'scale' : 1.0, 'min' : -10.0, 'max' : 10.0, 'free' : '0'},
    'Index1' :
        {'name' : 'Index1', 'value' : 2.0, 'scale' : -1.0, 'min' : 0.0, 'max' : 5.0, 'free' : '0'},
    'Index2' :
        {'name' : 'Index2', 'value' : 1.0, 'scale' : 1.0, 'min' : 0.0, 'max' : 2.0, 'free' : '0'},
    'LowerLimit' :
        {'name' : 'LowerLimit', 'value' : 100.0, 'scale' : 1.0, 'min' : 20.0, 'max' : 1000000., 'free' : '0'},
    'UpperLimit' :
        {'name' : 'UpperLimit', 'value' : 100000.0, 'scale' : 1.0, 'min' : 20.0, 'max' : 1000000., 'free' : '0'},
    }
    
def make_parameter_dict(pdict,fixed_par=False):

    o = copy.deepcopy(pdict)
    
    if not 'scale' in o or o['scale'] is None:
        value, scale = scale_parameter(o['value'])        
        o['value'] = value
        o['scale'] = scale

    if fixed_par:
        o['min'] = o['value']
        o['max'] = o['value']
        
    if float(o['min'])>float(o['value']):
        o['min'] = o['value']

    if float(o['max'])<float(o['value']):
        o['max'] = o['value']

    for k,v in o.items():
        o[k] = str(v)
        
    return o
    
    
def get_linear_dist(skydir,lon,lat,coordsys='CEL'):
    xy = sky_to_offset(skydir,np.degrees(lon),np.degrees(lat),
                       coordsys=coordsys)

    x = np.radians(xy[:,0])
    y = np.radians(xy[:,1])    
    delta = np.array([np.abs(x),np.abs(y)])
    dtheta = np.max(delta,axis=0)
    return dtheta
    
def get_dist_to_edge(skydir,lon,lat,width,coordsys='CEL'):

    xy = sky_to_offset(skydir,np.degrees(lon),np.degrees(lat),
                       coordsys=coordsys)

    x = np.radians(xy[:,0])
    y = np.radians(xy[:,1])
    
    delta_edge = np.array([np.abs(x) - width,np.abs(y) - width])
    dtheta = np.max(delta_edge,axis=0)
    return dtheta

def create_model_name(src):
    if src['SpectrumType'] == 'PowerLaw':
        return 'powerlaw_%04.2f'%src['Index']

class Model(object):
    """Base class for source objects."""
    
    def __init__(self,name,data=None,
                 spectral_pars=None,
                 spatial_pars=None):

        self._name = name
        self._data = {} if data is None else data
        self._spectral_pars = {} if spectral_pars is None else spectral_pars
        self._spatial_pars = {} if spatial_pars is None else spatial_pars

        self._names = [name]
        self._names_dict = {}
        for k in ROIModel.src_name_cols:

            if not k in self._data: continue            
            name = self._data[k].strip()
            if name != '' and not name in self._names:
                self._names.append(name)

            self._names_dict[k] = name
        
        
    def __contains__(self,key):
        return key in self._data

    def __getitem__(self,key):
        return self._data[key]

    def __setitem__(self,key,value):
        self._data[key]=value

    def __eq__(self, other): 
        return self.name == other.name

    @property
    def spectral_pars(self):
        return self._spectral_pars

    @property
    def spatial_pars(self):
        return self._spatial_pars

    @property
    def name(self):
        return self._name

    @property
    def names(self):
        return self._names

    def set_name(self,name,names=None):
        self._name = name
        if names is None:
            self._names = [name]
        else:
            self._names = names
    
    def add_name(self,name):
        self._names.append(name)
    
    def update(self,m):

        if self['SpectrumType'] != m['SpectrumType']:
            self._spectral_pars = {}
        
        self._data = merge_dict(self._data,m._data,add_new_keys=True)
        self._name = m.name
        self._names = list(set(self._names + m.names))        
        self._spectral_pars = merge_dict(self._spectral_pars,
                                         m._spectral_pars,add_new_keys=True)
        self._spatial_pars = merge_dict(self._spatial_pars,
                                        m._spatial_pars,add_new_keys=True)
        
class IsoSource(Model):

    def __init__(self,name,filefunction,spectral_pars=None,spatial_pars=None):
        super(IsoSource,self).__init__(name,None,spectral_pars,spatial_pars)
        
        self._filefunction = os.path.expandvars(filefunction)
        self['SpectrumType'] = 'FileFunction'

        if not self._spectral_pars:
            self._spectral_pars = {
                'Normalization' : {'name' : 'Normalization', 'scale' : '1.0',
                                   'value' : '1.0',
                                   'min' : '0.001', 'max' : '1000.0',
                                   'free' : '0' } }

        if not self._spatial_pars:            
            self._spatial_pars = {
                'Value' : {'name' : 'Value', 'scale' : '1',
                           'value' : '1', 'min' : '0', 'max' : '10',
                           'free' : '0' } }

        
        
    @property
    def filefunction(self):
        return self._filefunction

    def write_xml(self,root):
        
        source_element = create_xml_element(root,'source',
                                            dict(name=self.name,
                                                 type='DiffuseSource'))

        
        spec_el = create_xml_element(source_element,'spectrum',
                                     dict(file=self.filefunction,
                                          type='FileFunction',
                                          ctype='-1'))
                        
        spat_el = create_xml_element(source_element,'spatialModel',
                                     dict(type='ConstantValue'))


        for k,v in self._spectral_pars.items():                
            create_xml_element(spec_el,'parameter',v)

        for k,v in self._spatial_pars.items():                
            create_xml_element(spat_el,'parameter',v)
        
class MapCubeSource(Model):

    def __init__(self,name,mapcube,spectral_pars=None,spatial_pars=None):
        super(MapCubeSource,self).__init__(name,None,spectral_pars,spatial_pars)

        self._mapcube = os.path.expandvars(mapcube)
        self['SpectrumType'] = 'PowerLaw'

        if not self._spectral_pars:
            self._spectral_pars = {
                'Prefactor' : {'name' : 'Prefactor', 'scale' : '1',
                               'value' : '1.0', 'min' : '0.1', 'max' : '10.0',
                               'free' : '0' },
                'Index' : {'name' : 'Index', 'scale' : '-1',
                           'value' : '0.0', 'min' : '-1.0', 'max' : '1.0',
                           'free' : '0' },
                'Scale' : {'name' : 'Scale', 'scale' : '1',
                           'value' : '1000.0',
                           'min' : '1000.0', 'max' : '1000.0',
                           'free' : '0' },
                }

        if not self._spatial_pars:            
            self._spatial_pars = {
                'Normalization' :
                    {'name' : 'Normalization', 'scale' : '1',
                     'value' : '1', 'min' : '0', 'max' : '10',
                     'free' : '0' } }
        
    @property
    def mapcube(self):
        return self._mapcube

    def write_xml(self,root):
        
        source_element = create_xml_element(root,'source',
                                            dict(name=self.name,
                                                 type='DiffuseSource'))

        spec_el = create_xml_element(source_element,'spectrum',
                                     dict(type='PowerLaw'))
                        
        spat_el = create_xml_element(source_element,'spatialModel',
                                     dict(type='MapCubeFunction',
                                          file=self._mapcube))


        for k,v in self._spectral_pars.items():                
            create_xml_element(spec_el,'parameter',v)

        for k,v in self._spatial_pars.items():                
            create_xml_element(spat_el,'parameter',v)
        
class Source(Model):

    def __init__(self,name,data=None,
                 radec=None,
                 glonlat=None,
                 spectral_pars=None,
                 spatial_pars=None,
                 extended=False):
        super(Source,self).__init__(name,data,spectral_pars,spatial_pars)
                    
#        phi = np.radians(data['RAJ2000'])
#        theta = np.pi/2.-np.radians(data['DEJ2000'])

        self._radec = radec
        self._glonlat = glonlat

#        np.array([np.sin(theta)*np.cos(phi),
#                                np.sin(theta)*np.sin(phi),
#                                np.cos(theta)])


        ts_keys = ['Sqrt_TS30_100','Sqrt_TS100_300',
                   'Sqrt_TS300_1000','Sqrt_TS1000_3000',
                   'Sqrt_TS3000_10000','Sqrt_TS10000_100000']

        if ts_keys[0] in self:        
            self._data['TS_value'] = 0
            for k in ts_keys:
                if k in self and np.isfinite(self[k]):
                    self._data['TS_value'] += self[k]**2


        self._extended=extended

        if not self._spectral_pars:
            self._update_spectral_pars()

        if not self._spatial_pars:
            self._update_spatial_pars()

#        if 'name' in self._data and self._data['name'] is not None:
#            self._data['Source_Name'] = self._data.pop('name')
#        if not 'Source_Name' in self._data:
#            self._data['Source_Name'] = create_model_name(self)
            

            
    def _update_spatial_pars(self):

        if not self.extended:
            self._data['SpatialType'] = 'PointSource'
            self._spatial_pars = {
                'RA' : {'name' : 'RA',  'value' : str(self['RAJ2000']),
                        'free' : '0',
                        'min' : '-360.0','max' : '360.0','scale' : '1.0'},
                'DEC' : {'name' : 'DEC',  'value' : str(self['DEJ2000']),
                         'free' : '0',
                         'min' : '-90.0','max' : '90.0','scale' : '1.0'}
                }
        else:

            self._spatial_pars = {
                'Prefactor' : {'name' : 'Prefactor', 'value' : '1',
                               'free' : '0', 'min' : '0.001', 'max' : '1000',
                               'scale' : '1.0'}
                }
            
    def _update_spectral_pars(self):

        self._spectral_pars = {}        
        sp = self._spectral_pars
        
        if self['SpectrumType'] == 'PowerLaw':

            sp['Prefactor'] = copy.copy(default_par_dict['Prefactor'])
            sp['Scale'] = copy.copy(default_par_dict['Scale'])
            sp['Index'] = copy.copy(default_par_dict['Index'])
            
            sp['Prefactor']['value'] = self['Flux_Density']
            sp['Scale']['value'] = self['Pivot_Energy']
            sp['Index']['value'] = self['Spectral_Index']                           
            sp['Index']['max'] = max(5.0,sp['Index']['value']+1.0)
            sp['Index']['min'] = min(0.0,sp['Index']['value']-1.0)
                        
            sp['Prefactor'] = make_parameter_dict(sp['Prefactor'])
            sp['Scale'] = make_parameter_dict(sp['Scale'],True)
            sp['Index'] = make_parameter_dict(sp['Index'])

        elif self['SpectrumType'] == 'LogParabola':

            sp['norm'] = copy.copy(default_par_dict['norm'])
            sp['Eb'] = copy.copy(default_par_dict['Eb'])
            sp['alpha'] = copy.copy(default_par_dict['alpha'])
            sp['beta'] = copy.copy(default_par_dict['beta'])

            sp['norm']['value'] = self['Flux_Density']
            sp['Eb']['value'] = self['Pivot_Energy']
            sp['alpha']['value'] = self['Spectral_Index']
            sp['beta']['value'] = self['beta']
                        
            sp['norm'] = make_parameter_dict(sp['norm'])
            sp['Eb'] = make_parameter_dict(sp['Eb'],True)
            sp['alpha'] = make_parameter_dict(sp['alpha'])
            sp['beta'] = make_parameter_dict(sp['beta'])            
        
        elif self['SpectrumType'] == 'PLSuperExpCutoff':

            flux_density = self['Flux_Density']
            flux_density *= np.exp((self['Pivot_Energy']/self['Cutoff'])**self['Exp_Index'])
            
            sp['Prefactor'] = copy.copy(default_par_dict['Prefactor'])
            sp['Index1'] = copy.copy(default_par_dict['Index1'])
            sp['Index2'] = copy.copy(default_par_dict['Index2'])
            sp['Scale'] = copy.copy(default_par_dict['Scale'])
            sp['Cutoff'] = copy.copy(default_par_dict['Cutoff'])

            sp['Prefactor']['value'] = flux_density
            sp['Index1']['value'] = self['Spectral_Index']
            sp['Index2']['value'] = self['Exp_Index']
            sp['Scale']['value'] = self['Pivot_Energy']
            sp['Cutoff']['value'] = self['Cutoff']
            
            sp['Prefactor'] = make_parameter_dict(sp['Prefactor'])
            sp['Scale'] = make_parameter_dict(sp['Scale'],True)
            sp['Index1'] = make_parameter_dict(sp['Index1'])
            sp['Index2'] = make_parameter_dict(sp['Index2'])
            sp['Cutoff'] = make_parameter_dict(sp['Cutoff'])                

        else:

            import pprint
            pprint.pprint(self._data)            
            raise Exception('Unsupported spectral type:' + self['SpectrumType'])
        
    def set_position(self,skydir):

        if not isinstance(skydir,SkyCoord):
            skydir = SkyCoord(ra=skydir[0],dec=skydir[1],unit=u.deg)
        
        self._radec = np.array([skydir.ra.deg,skydir.dec.deg])
        self._glonlat = np.array([skydir.galactic.l.deg,skydir.galactic.b.deg])

    def set_spatial_model(self,spatial_model,spatial_width):

        self._data['SpatialModel'] = spatial_model
        self._data['SpatialWidth'] = spatial_width
        
        if self['SpatialModel'] == 'PointSource' or self['SpatialModel'] == 'Gaussian':
            self._extended = False
            self._data['SpatialType'] = 'PointSource'
        elif self['SpatialModel'] == 'PSFSource' or self['SpatialModel'] == 'CGaussianSource':
            self._extended = True
            self._data['SpatialType'] = 'MapCubeFunction'
        elif self['SpatialModel'] == 'GaussianSource':
            self._extended = True
            self._data['SpatialType'] = 'SpatialMap'
        elif self['SpatialModel'] == 'DiskSource':
            self._extended = True
            self._data['SpatialType'] = 'SpatialMap'
        else:
            raise Exception('Unrecognized SpatialModel: ' + self['SpatialModel'] +
                            '\n Valid choices are: PointSource, GaussianSource, DiskSource ')
        
        self._update_spatial_pars()
        
    def check_cuts(self,cuts):

        if isinstance(cuts,tuple): cuts = [cuts]
        
        for c in cuts:

            if not isinstance(c,tuple) or len(c) != 3:
                raise Exception('Wrong format for cuts tuple.')
            
            (pname,pmin,pmax) = c
            if not pname in self._data: return False
            if pmin is not None and self[pname] < pmin: return False
            if pmax is not None and self[pname] > pmax: return False

        return True
                               
    def separation(self,src):

        if isinstance(src,Source):
            return self.radec.separation(src.skydir)
        else:
            return self.radec.separation(src)
    
    @property
    def extended(self):
        return self._extended

    @property
    def associations(self):
        return self._names

    @property
    def radec(self):
        return self._radec

    @property
    def skydir(self):
        return SkyCoord(self._radec[0]*u.deg,self._radec[1]*u.deg)
    
    @property
    def data(self):
        return self._data

    @staticmethod
    def create_from_dict(src_dict):
        """Create a source object from a python dictionary."""

        import pprint
        
        src_dict = copy.deepcopy(src_dict)
        spectrum_type = src_dict.get('SpectrumType','PowerLaw')
        
        default_src_dict = dict(name = None,
                                Source_Name = None,
                                SpatialModel = 'PointSource',
                                SpatialWidth = 0.5,
                                SpectrumType = 'PowerLaw',
                                ra = None,
                                dec = None,
                                glon = None,
                                glat = None,
                                spectral_pars = {})

        for p in spectrum_type_pars[spectrum_type]:
            default_src_dict['spectral_pars'][p] = copy.copy(default_par_dict[p])

        for k,v in default_par_dict.items():
            
            if not k in src_dict: continue
            src_dict.setdefault('spectral_pars',{})
            src_dict['spectral_pars'].setdefault(k,{})
            
            if not isinstance(src_dict[k],dict):
                src_dict['spectral_pars'][k] = {'name' : k, 'value' : src_dict.pop(k)}
            else:
                src_dict['spectral_pars'][k] = src_dict.pop(k)
            
        src_dict = merge_dict(default_src_dict,src_dict)        
        for k, v in src_dict['spectral_pars'].items():
            src_dict['spectral_pars'][k] = make_parameter_dict(v)
        
#        validate_config(src_dict,default_src_dict)

        if src_dict['SpatialModel'] != 'PointSource':
            extended=True
        else:
            extended=False
        
        if 'name' in src_dict:
            name = src_dict['name']
            src_dict['Source_Name'] = src_dict.pop('name')
        elif 'Source_Name' in src_dict:
            name = src_dict['Source_Name']
        else:
            raise Exception('Source name undefined.')
            
        skydir = get_target_skydir(src_dict)
        
        src_dict['RAJ2000'] = skydir.ra.deg
        src_dict['DEJ2000'] = skydir.dec.deg
        
        radec = np.array([skydir.ra.deg,skydir.dec.deg])
        return Source(name,src_dict,radec=radec,extended=extended,
                      spectral_pars=src_dict['spectral_pars'])
    
    @staticmethod
    def create_from_xml(root,extdir=None):
        
        spec = load_xml_elements(root,'spectrum')
        spat = load_xml_elements(root,'spatialModel')
        spectral_pars = load_xml_elements(root,'spectrum/parameter')
        spatial_pars = load_xml_elements(root,'spatialModel/parameter')

        src_type = root.attrib['type']
        spatial_type = spat['type']
        spectral_type = spec['type']
        
        src_dict = copy.deepcopy(root.attrib)

        src_dict['Source_Name'] = src_dict['name']
        src_dict['SpectrumType'] = spec['type']
            
        if src_type =='PointSource' or spatial_type == 'SpatialMap':
        
            extflag=False        
            if 'file' in spat: 
                src_dict['Spatial_Filename'] = spat['file']
                extflag=True

                if not os.path.isfile(src_dict['Spatial_Filename']) \
                        and extdir is not None:
                    src_dict['Spatial_Filename'] = \
                        os.path.join(extdir,'Templates',
                                     src_dict['Spatial_Filename'])

            
            
            if 'RA' in src_dict:
                src_dict['RAJ2000'] = float(src_dict['RA'])
                src_dict['DEJ2000'] = float(src_dict['DEC'])
            elif 'RA' in spatial_pars:
                src_dict['RAJ2000'] = float(spatial_pars['RA']['value'])
                src_dict['DEJ2000'] = float(spatial_pars['DEC']['value'])
            else:
                hdu = pyfits.open(src_dict['Spatial_Filename'])
                src_dict['RAJ2000'] = float(hdu[0].header['CRVAL1'])
                src_dict['DEJ2000'] = float(hdu[0].header['CRVAL2'])

            radec = np.array([src_dict['RAJ2000'],src_dict['DEJ2000']])
                
            return Source(src_dict['Source_Name'],
                          src_dict,radec=radec,
                          spectral_pars=spectral_pars,
                          spatial_pars=spatial_pars,extended=extflag)

        elif src_type == 'DiffuseSource' and spatial_type == 'ConstantValue':
            return IsoSource(src_dict['Source_Name'],spec['file'],
                             spectral_pars,spatial_pars)
        elif src_type == 'DiffuseSource' and spatial_type == 'MapCubeFunction':
            return MapCubeSource(src_dict['Source_Name'],spat['file'],
                                 spectral_pars,spatial_pars)
        else:
            raise Exception('Unrecognized type for source: %s'%src_dict['Source_Name'])
        
    def write_xml(self,root):
        
        if not self.extended:
            source_element = create_xml_element(root,'source',
                                                dict(name=self['Source_Name'],
                                                     type='PointSource'))
            
            spat_el = ElementTree.SubElement(source_element,'spatialModel')
            spat_el.set('type','SkyDirFunction')
             
        else:
            source_element = create_xml_element(root,'source',
                                                dict(name=self['Source_Name'],
                                                     type='DiffuseSource'))
            
            spat_el = create_xml_element(source_element,'spatialModel',
                                         dict(map_based_integral='True',
                                              type='SpatialMap',
                                              file=self['Spatial_Filename']))
                    
        for k,v in self._spatial_pars.items():                
            create_xml_element(spat_el,'parameter',v)

                
        el = ElementTree.SubElement(source_element,'spectrum')  
        
        stype = self['SpectrumType'].strip()            
        el.set('type',stype)

#        spec_element.set('type','PLSuperExpCutoff')
        
        for k,v in self._spectral_pars.items():                
            create_xml_element(el,'parameter',v)
    
class ROIModel(AnalysisBase):
    """This class is responsible for managing the ROI definition.
    Catalogs can be read from either FITS or XML files."""

    defaults = dict(defaults.model.items(),
                    logfile=(None,''),
                    fileio=defaults.fileio,
                    logging=defaults.logging)

    src_name_cols = ['Source_Name',
                     'ASSOC1','ASSOC2','ASSOC_GAM',
                     '1FHL_Name','2FGL_Name',
                     'ASSOC_GAM1','ASSOC_GAM2','ASSOC_TEV']

    def __init__(self,config=None,srcs=None,diffuse_srcs=None,**kwargs):
        # Coordinate for ROI center (defaults to 0,0)
        self._skydir = kwargs.pop('skydir',SkyCoord(0.0,0.0,unit=u.deg)) 

        super(ROIModel,self).__init__(config,**kwargs)
        
        self.logger = Logger.get(self.__class__.__name__,
                                 self.config['logfile'],
                                 ll(self.config['logging']['verbosity']))
        
        if not os.path.isdir(self.config['extdir']):
            self._config['extdir'] = \
                os.path.join(fermipy.PACKAGE_ROOT,
                             'catalogs',self.config['extdir'])
        
        self._srcs = []
        self._diffuse_srcs = []
        self._src_index = {}
        self._src_radius = []

        if srcs is None: srcs = []
        if diffuse_srcs is None: diffuse_srcs = []
            
        for s in srcs + diffuse_srcs:
            self.load_source(s)
        
        self.build_src_index()

    def __iter__(self):
        return iter(self._srcs + self._diffuse_srcs)

    @property
    def skydir(self):
        """Return the sky direction objection corresponding to the
        center of the ROI."""        
        return self._skydir

    @property
    def sources(self):
        return self._srcs

    @property
    def diffuse_sources(self):
        return self._diffuse_srcs
    
    def load_diffuse_srcs(self):

        self._load_diffuse_src('isodiff')
        self._load_diffuse_src('galdiff')
        self._load_diffuse_src('limbdiff')
        self._load_diffuse_src('diffuse')

    def _load_diffuse_src(self,name,src_type='FileFunction'):

        srcs = []
        if self.config[name] is not None:
            srcs = self.config[name]

        for i, t in enumerate(srcs):
            
            if isinstance(t,str):
                src_dict = {'file' : t}
            elif isinstance(t,dict):
                src_dict = copy.deepcopy(t)
                
            if not 'name' in src_dict:                
                if len(srcs) == 1:
                    src_dict['name'] = name
                else:
                    src_dict['name'] = name + '%02i'%i
                    
            if re.search(r'(\.txt$)',src_dict['file']):
                src_type = 'FileFunction'
            elif re.search(r'(\.fits$|\.fit$|\.fits.gz$|\.fit.gz$)',src_dict['file']):
                src_type = 'MapCubeFunction'
            else:
                raise Exception('Unrecognized file format for diffuse model: %s'%src_dict['file'])

            if src_type == 'FileFunction':                    
                src = IsoSource(src_dict['name'],src_dict['file'])
                altname = os.path.basename(src_dict['file'])            
                altname = re.sub(r'(\.txt$)','', altname)
            else:
                src = MapCubeSource(src_dict['name'],src_dict['file'])
                altname = os.path.basename(src_dict['file'])
                altname = re.sub(r'(\.fits$|\.fit$|\.fits.gz$|\.fit.gz$)',
                                 '', altname)    
                
                
            src.add_name(altname)            
            self.load_source(src)


    def create_source(self,src_dict,build_index=True):
        """Create a new source object from a source dictionary and
        load it in the ROI."""
        

        src = Source.create_from_dict(src_dict)
        src.set_spatial_model(src['SpatialModel'],src['SpatialWidth'])
        
        self.logger.info('Creating source ' + src.name)
        self.logger.debug(src._data)

        self.load_source(src)
        if build_index: self.build_src_index()

        return src
        
    def load_source(self,src):

        name = src.name.replace(' ','').lower()
        
        if name in self._src_index:
            self.logger.info('Updating source model for %s'%src.name)
            self._src_index[name].update(src)
            return

        self._src_index[src.name] = src

        for name in src.names:
            self._src_index[name.replace(' ','').lower()] = src

        if isinstance(src,Source):
            self._srcs.append(src)
        else:
            self._diffuse_srcs.append(src)
            
    def load(self):

        self._srcs = []
        self.load_diffuse_srcs()
            
        for c in self.config['catalogs']:

            extname = os.path.splitext(c)[1]            
            if extname == '.fits' or extname == '.fit':
                self.load_fits(c)
            elif extname == '.xml':
                self.load_xml(c)
            else:
                raise Exception('Unrecognized catalog file extension: %s'%c)

        for c in self.config['sources']:
            self.create_source(c,build_index=False)

        self.build_src_index()        
        
    def delete_sources(self,srcs):
        
        self._src_index = {k:v for k,v in self._src_index.items() if not v in srcs}
        self._srcs = [s for s in self._srcs if not s in srcs]
        self._diffuse_srcs = [s for s in self._diffuse_srcs if not s in srcs]
        self.build_src_index()

    @staticmethod
    def create(selection,config,**kwargs):
        if selection['target'] is not None:            
            return ROIModel.create_from_source(selection['target'],
                                               config,**kwargs)
        else:
            target_skydir = get_target_skydir(selection)
            return ROIModel.create_from_position(target_skydir,
                                                 config,**kwargs)
        
    # Creation Methods           
    @staticmethod
    def create_from_position(skydir,config,**kwargs):
        """Create an ROI centered on the given coordinates."""

        roi = kwargs.pop('roi',None)
        if roi is None:        
            roi = ROIModel(config,**kwargs)
            roi.load()

        srcs_dict = {}
            
        if roi.config['src_radius'] is not None:        
            rsrc, srcs = roi.get_sources_by_position(skydir,
                                                     roi.config['src_radius'])
            for s,r in zip(srcs,rsrc):
                srcs_dict[s.name] = (s,r)

        if roi.config['src_roiwidth'] is not None:                
            rsrc, srcs = \
                roi.get_sources_by_position(skydir,
                                            roi.config['src_roiwidth']/2.,
                                            square=True)
                
            for s,r in zip(srcs,rsrc):
                srcs_dict[s.name] = (s,r)

        srcs = []
        rsrc = []
        
        for k, v in srcs_dict.items():
            srcs.append(v[0])
            rsrc.append(v[1])
        
        return ROIModel(config,srcs=srcs,
                        diffuse_srcs=roi._diffuse_srcs,
                        skydir=skydir,**kwargs)
        
        
    @staticmethod
    def create_from_source(name,config,**kwargs):
        """Create an ROI centered on the given source."""

        roi = ROIModel(config,**kwargs)
        roi.load()
        src = roi.get_source_by_name(name)

        return ROIModel.create_from_position(src.skydir,config,
                                             roi=roi,**kwargs)
        
    @staticmethod
    def create_roi_from_ft1(ft1file,config):
        """Create an ROI model by extracting the sources coordinates
        form an FT1 file."""
        pass            
                
    def get_source_by_name(self,name):
        """Retrieve source by name."""

        index_name = name.replace(' ','').lower()
        
        if index_name in self._src_index:
            return self._src_index[index_name]
        else:
            raise Exception('No source matching name: ' + name)

    def get_nearby_sources(self,name,dist,min_dist=None,
                           square=False):
        
        src = self.get_source_by_name(name)
        return self.get_sources_by_position(src.skydir,
                                            dist,min_dist,
                                            square)

    def get_sources(self,cuts=None,distance=None,square=False):
        """Retrieve list of sources satisfying the given selections."""
        rsrc, srcs = self.get_sources_by_position(self.skydir,
                                                  distance,
                                                  square=square)
        o = []
        if cuts is None: cuts = []        
        for s,r in zip(srcs,rsrc):
            if not s.check_cuts(cuts): continue            
            o.append(s)

        return o
    
    def get_sources_by_property(self,pname,pmin,pmax=None):

        srcs = []
        for i, s in enumerate(self._srcs):
            if not pname in s: continue
            if pmin is not None and s[pname] < pmin: continue
            if pmax is not None and s[pname] > pmax: continue
            srcs.append(s)
        return srcs
    
    def get_sources_by_position(self,skydir,dist,min_dist=None,
                                square=False):
        """Retrieve sources within a certain angular distance of an
        (ra,dec) coordinate.  This function supports two types of
        geometric selections: circular (square=False) and square
        (square=True).  The circular selection finds all sources with a given
        angular distance of the target position.  The square selection
        finds sources within an ROI-like region of size R x R where R
        = 2 x dist.

        Parameters
        ----------

        skydir : SkyCoord object
            Sky direction with respect to which the selection will be applied.

        dist : float
            Maximum distance in degrees from the sky coordinate.

        square : bool
            Choose whether to apply a circular or square selection.
        
        """

        if dist is None: dist = 180.
        
        radius = self._src_skydir.separation(skydir).rad
        
        if not square:                    
            dtheta = radius            
        else:
            dtheta = get_linear_dist(skydir,
                                     self._src_skydir.ra.rad,
                                     self._src_skydir.dec.rad)
        
        if min_dist is not None:
            msk = np.where((dtheta < np.radians(dist)) &
                           (dtheta > np.radians(min_dist)))[0]
        else:
            msk = np.where(dtheta < np.radians(dist))[0]

        radius = radius[msk]
        dtheta = dtheta[msk]
        srcs = [ self._srcs[i] for i in msk ]
            
        isort = np.argsort(radius)

        radius = radius[isort]
        srcs = [srcs[i] for i in isort]
        
        return radius, srcs
    
    def load_fits(self,fitsfile,
                  src_hduname='LAT_Point_Source_Catalog',
                  extsrc_hduname='ExtendedSources'):
        """Load sources from a FITS catalog file."""

        if not os.path.isfile(fitsfile):
            fitsfile = os.path.join(fermipy.PACKAGE_ROOT,'catalogs',fitsfile)
        
        hdulist = pyfits.open(fitsfile)
        table_src = hdulist[src_hduname]
        table_extsrc = hdulist[extsrc_hduname]

        # Rearrange column data in a more convenient format
        cols = fits_recarray_to_dict(table_src)
        cols_extsrc = fits_recarray_to_dict(table_extsrc)

        extsrc_names = cols_extsrc['Source_Name'].tolist()
        extsrc_names = [s.strip() for s in extsrc_names]

        src_skydir = SkyCoord(ra=cols['RAJ2000']*u.deg,
                             dec=cols['DEJ2000']*u.deg)

        radec = np.vstack((src_skydir.ra.deg,src_skydir.dec.deg)).T
        glonlat = np.vstack((src_skydir.galactic.l.deg,src_skydir.galactic.b.deg)).T
        
        nsrc = len(table_src.data)
        for i in range(nsrc):

            src_dict = {}
            for icol, col in enumerate(cols):
                src_dict[col] = cols[col][i]

            extflag=False

            src_dict['Source_Name'] = src_dict['Source_Name'].strip()  
            extsrc_name = src_dict['Extended_Source_Name'].strip()

            if len(extsrc_name.strip()) > 0:
                extflag=True
                extsrc_index = extsrc_names.index(extsrc_name) 
                
                for icol, col in enumerate(cols_extsrc):
                    if col in cols: continue
                    src_dict[col] = cols_extsrc[col][extsrc_index]

                src_dict['Spatial_Filename'] = src_dict['Spatial_Filename'].strip()

                if not os.path.isfile(src_dict['Spatial_Filename']) and self.config['extdir']:
                    src_dict['Spatial_Filename'] = os.path.join(self.config['extdir'],
                                                                'Templates',
                                                                src_dict['Spatial_Filename'])
            
            src_dict['SpectrumType'] = src_dict['SpectrumType'].strip()
            if src_dict['SpectrumType'] == 'PLExpCutoff':
                src_dict['SpectrumType'] = 'PLSuperExpCutoff'
            
            src = Source(src_dict['Source_Name'],src_dict,radec=radec[i],glonlat=glonlat[i],extended=extflag)
            self.load_source(src)
            
        self.build_src_index()

#            cat.load_source(ROIModelSource(src))

    def build_src_index(self):
        """Build an indices for fast lookup of a source given its name
        or coordinates."""
        
        nsrc = len(self._srcs)
        radec = np.zeros((2,nsrc))
        
        for i, s in enumerate(self._srcs):
            radec[:,i] = s.radec

        self._src_skydir = SkyCoord(ra=radec[0],dec=radec[1],unit=u.deg)
        self._src_radius = self._src_skydir.separation(self.skydir)
        
        for i, s in enumerate(self._diffuse_srcs):
            pass
        
    def write_xml(self,xmlfile):
        """Save this ROI model as an XML file."""
        
        root = ElementTree.Element('source_library')
        root.set('title','source_library')

        for s in self._srcs:
            s.write_xml(root)
                
        for s in self._diffuse_srcs:
            s.write_xml(root)
                
        output_file = open(xmlfile,'w')
        output_file.write(prettify_xml(root))

    def load_xml(self,xmlfile):
        """Load sources from an XML file."""

        if not os.path.isfile(xmlfile):
            xmlfile = os.path.join(fermipy.PACKAGE_ROOT,'catalogs',xmlfile)

        self.logger.info('Reading XML Model: ' + xmlfile)
            
        root = ElementTree.ElementTree(file=xmlfile).getroot()

        for s in root.findall('source'):
            src = Source.create_from_xml(s,extdir=self.config['extdir'])
            self.load_source(src)

        self.build_src_index()

if __name__ == '__main__':

    
    roi = ROIModel()


    roi.load_fits('gll_fssc_psc_v14.fit')


    src = roi.get_source_by_name('lmc')


    import pprint
    pprint.pprint(src.data)

    print src

    srcs = roi.get_nearby_sources('lmc',10.0)

#    for s in srcs:        
#        print s.name, s.associations, s.separation(src)

    roi.create_roi_from_source('test.xml','lmc','test','test',90.0)
