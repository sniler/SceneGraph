#!/usr/bin/env python
import os
import sys
import uuid
import simplejson as json
from collections import OrderedDict as dict
from collections import MutableMapping
from SceneGraph.core import log, Attribute, Observable
from SceneGraph.options import SCENEGRAPH_PATH, SCENEGRAPH_PLUGIN_PATH
from SceneGraph import util


PROPERTY_TYPES = dict(
    simple              = ['FLOAT', 'STRING', 'BOOL', 'INT'],
    arrays              = ['FLOAT2', 'FLOAT3', 'INT2', 'INT3', 'COLOR'],
    data_types          = ['FILE', 'MULTI', 'MERGE', 'NODE', 'DIR'],   
    )


class DagNode(Observable):

    default_name  = 'node'
    default_color = [172, 172, 172, 255]
    node_type     = 'dagnode'
    PRIVATE       = ['node_type']
    required      = ['name', 'color', 'docstring', '_graph', 'width', 
                     'width', 'base_height', 'pos', 'enabled', 'orientation',
                     '_metadata', 'data']

    def __init__(self, name=None, **kwargs):
        self._attributes        = dict()

        Observable.__init__(self)
        self._metadata          = Metadata(self)

        # basic node attributes        
        self.name               = name if name else self.default_name
        self.color              = kwargs.pop('color', self.default_color)
        self.docstring          = ""
        self._graph             = kwargs.pop('_graph', None)

        self.width              = kwargs.pop('width', 100.0)
        self.base_height        = kwargs.pop('base_height', 15.0)

        self.pos                = kwargs.pop('pos', (0.0, 0.0))
        self.enabled            = kwargs.pop('enabled', True)
        self.orientation        = kwargs.pop('orientation', 'horizontal')

        # metadata
        metadata                = kwargs.pop('metadata', dict())
        attributes              = kwargs.pop('attributes', dict())

        # if the node metadata isn't passed from another class, 
        # read it from disk
        if not metadata:
            metadata = self.parse_metadata()
        # ui
        self._widget            = None  

        UUID = kwargs.pop('id', None)
        self.id = UUID if UUID else str(uuid.uuid4())
        self._metadata.update(metadata)

        # attributes
        self.buildAttributes()

        # add attributes
        if attributes:
            for attr_name, properties in attributes.iteritems():
                if attr_name in self._attributes:
                    self._attributes.get(attr_name).update(**properties)
                else:
                    self.add_attr(attr_name, **properties)

    def __str__(self):
        return json.dumps(self.data, default=lambda obj: obj.data, indent=4)

    def __repr__(self):
        return json.dumps(self.data, default=lambda obj: obj.data, indent=4)
    
    def __getattr__(self, name):
        if name in self._attributes:
            attribute = self._attributes.get(name)
            #print 'querying Attribute: "%s"' % name
            return attribute.value
        elif hasattr(self, name):
            return getattr(self, name)
        raise AttributeError('no attribute exists "%s"' % name)

    def __setattr__(self, name, value):
        if name in ['_attributes', '_changed', '_observers']:
            super(DagNode, self).__setattr__(name, value)
        elif name in self._attributes:
            attribute = self._attributes.get(name)
            if value != attribute.value:
                attribute.value = value
                # callbacks
                Observable.set_changed(self)
                Observable.notify(self)
        else:
            super(DagNode, self).__setattr__(name, value)
            # callbacks
            Observable.set_changed(self)
            Observable.notify(self)        

    @property
    def data(self):
        """
        Output data for writing.
        """
        data = dict()
        for attr in ['name', 'node_type', 'id', 'color', 'width', 'base_height', 'pos', 'enabled', 'orientation']:
            if hasattr(self, attr):
                data[attr] = getattr(self, attr)
        data.update(**self._attributes)
        return data

    def connect_widget(self, widget):
        """
        Connect a widget to the dag.

        params:
            widget (obj) - NodeWidget class
        """
        if not self._widget:
            self._widget = widget
            self.add_observer(widget)
            return True
        return False

    @property
    def metadata(self):
        """
        Output metadata object.
        """
        return self._metadata

    @property 
    def template(self):
        print json.dumps(self._metadata._template_data, indent=5)

    @property
    def graph(self):
        return self._graph

    @graph.setter
    def graph(self, value):
        self._graph = value
        return self.graph

    #- Virtual ----
    def evaluate(self):
        """
        Evalutate the node.
        """
        return True

    #- Transform ----
    @property
    def expanded(self):
        height = max(len(self.inputs), len(self.outputs))
        return height > 1

    @property
    def height(self):
        """
        Returns the height of the node (height is determined 
        as base height * max number of connectable attributes)

        returns:
            (float) - total height of the node.
        """
        btm_buffer = 0
        max_conn = max(len(self.inputs), len(self.outputs))
        height = max_conn if max_conn else 1
        if height > 1:
            height+=1
            btm_buffer = self.base_height/2
        return (height * self.base_height) + btm_buffer

    @height.setter
    def height(self, value):
        """
        Set the base height value.

        params:
            value (float) = base height.
        """
        self.base_height=value

    #- Attributes ----
    def attributes(self, *args):
        """
        Returns a dictionary of connections attributes.

        returns:
            (dict) - { connection name: Attribute }
        """
        if not args:
            return self._attributes.values()
        else:
            attrs = [x for x in self._attributes.values() if x.name in args]
            if attrs and len(attrs) == 1:
                return attrs[0]
            return attrs

    def add_attr(self, name, value=None, **kwargs):
        """
        Add an attribute.

         * todo: add attribute type mapper.
        """
        attr = Attribute(name, value, dagnode=self, **kwargs)
        self._attributes.update({attr.name:attr})
        return attr

    def get_attr(self, name):
        """
        Return a named attribute.

        params:
            name (str) - name of attribute.
        """
        if name not in self._attributes:
            self.add_attr(name)
        return self._attributes.get(name)

    def rename_attr(self, name, new_name):
        """
        Rename an attribute.

        params:
            name     (str) - name of attribute.
            new_name (str) - new name.
        """
        if name not in self._attributes:
            raise AttributeError(name)

        if hasattr(self, new_name):
            raise AttributeError('attribute "%s" already exists.' % new_name)

        attr = self._attributes.pop(name)
        attr.name = new_name
        self._attributes.update({attr.name:attr})

    #- Connections ----
    def buildAttributes(self, verbose=False):
        """
        Parse and build attributes.
        """
        if verbose:
            print '\n# "%s:%s":' % (self.Class(), self.name)

        for section in self._metadata.data:
            if verbose:
                print '   "Section: %s"' % ( section)

            attributes = self._metadata.data.get(section)

            for attr_name in attributes:
                
                # parse connections
                properties = attributes.get(attr_name)
                attr_label = 'Attribute'

                is_connection = False
                conn_type = None
                required  = False


                if 'connectable' in properties:
                    if 'connection_type' in properties:
                        is_connection = True
                        conn_type = properties.get('connection_type')
                        if conn_type == 'input':
                            attr_label = "Input"

                        if conn_type == 'output':
                            attr_label = "Output"

                # parse required
                if 'required' in properties:
                    required = properties.get('required', False)

                if required:
                    attr_label = '*%s' % attr_label

                if verbose:
                    print '      "%s: %s"' % (attr_label, attr_name)

                # build an attribute
                if is_connection:
                    attr_node = self.metadata.map(attr_name, properties)
                    if not attr_node:
                        continue

                # parse properties of attribute/connection
                # MAPPING:
                # name    -> name
                # type    -> attr_type (lower)
                # default -> default_value
                # label   -> label
                for pname in properties:
                    if pname not in ['required']:
                        pvalues = properties.get(pname)

                        # connection data, pass
                        if not util.is_dict(pvalues):
                            continue 

                        if verbose:
                            print '         "%s":' % (pname)
                        for pattr in pvalues:
                            pval = pvalues.get(pattr)
                            if verbose:
                                print '             "%s":%s' % (pattr, pval)
            if verbose:
                print '\n'


    @property
    def connections(self):
        """
        Returns a list of connections (input & output)

        returns:
            (list) - list of connection names.
        """
        conn_names = []
        for name in self._attributes:
            if self._attributes.get(name).connectable:
                conn_names.append(name)
        return conn_names

    @property
    def inputs(self):
        """
        Returns a list of input connection names.

        returns:
            (list) - list of input connection names.
        """
        connections = []
        for name in self._attributes:
            data = self._attributes.get(name)
            #if data.get('connectable') and data.get('connection_type') == 'output':
            if data.connectable and data.connection_type == 'input':
                connections.append(name)
        return connections

    @property
    def outputs(self):
        """
        Returns a list of output connection names.

        returns:
            (list) - list of output connection names.
        """
        connections = []
        for name in self._attributes:
            data = self._attributes.get(name)
            #if data.get('connectable') and data.get('connection_type') == 'output':
            if data.connectable and data.connection_type == 'output':
                connections.append(name)
        return connections

    def get_input(self, name='input'):
        """
        Return a named node input.

        params:
            name (str) - name of input.

        returns:
            (Connection) - connection node.
        """
        if not name in self._attributes:
            return

        data = self._attributes.get(name)
        if data.connectable and data.connection_type == 'input':
            return self._attributes.get(name)
        return

    def get_output(self, name='output'):
        """
        Return a named node output.

        params:
            name (str) - name of output.

        returns:
            (Connection) - connection node.
        """
        if not name in self._attributes:
            return

        data = self._attributes.get(name)
        if data.connectable and data.connection_type == 'output':
            return self._attributes.get(name)
        return

    def is_connected(self, name):
        """
        Returns true if the named connection has 
        a connection.

        params:
            name (str) - name of connection to query.

        returns:
            (bool) - connection status.
        """
        conn = self.get_connection(name)
        if not conn:
            return False
        return not conn.connectable

    def input_connections(self):
        """
        Returns a list of connected DagNodes.

        returns:
            (list) - list of DagNode objects.
        """
        connected_nodes = []
        for edge in self.graph.network.edges(data=True):
            # edge = (id, id, {atttributes})
            srcid, destid, attrs = edge
            if destid == self.id:
                if srcid in self.graph.dagnodes:
                    connected_nodes.append(self.graph.dagnodes.get(srcid))
        return connected_nodes

    def output_connections(self):
        """
        Returns a list of connected DagNodes.

        returns:
            (list) - list of DagNode objects.
        """
        connected_nodes = []
        for edge in self.graph.network.edges(data=True):
            # edge = (id, id, {atttributes})
            srcid, destid, attrs = edge
            if srcid == self.id:
                if destid in self.graph.dagnodes:
                    connected_nodes.append(self.graph.dagnodes.get(destid))
        return connected_nodes

    @property
    def is_input_connection(self):
        """
        Returns true if the node is an input connection.

        returns:
            (bool) - node has input connections.
        """
        return bool(self.output_connections())
 
    @property
    def is_output_connection(self):
        """
        Returns true if the node is an output connection.

        returns:
            (bool) - node has output connections.
        """
        return bool(self.input_connections())   

    def get_connection(self, name):
        """
        Returns a named connection (input or output).

        params:
            name (str) - name of connection to query.

        returns:
            (Attribute) - connection object.
        """
        conn = None
        if name not in self._attributes:
            return 

        data = self._attributes.get(name)
        if data.connectable:
            return data
        return

    def rename_connection(self, old, new):
        """
        Rename a connection.

        params:
            old (str) - old connection name.
            new (new) - new connection name.

        returns:
            (bool) - rename was successful.
        """
        conn = self.get_connection(old)
        if conn:
            conn.name = new
            return True
        return False

    def remove_connection(self, name):
        """
        Remove a named connection (input or output).

        params:
            name (str) - name of connection to query.

        returns:
            (bool) - connection was removed.
        """
        conn = self.get_connection(name)
        if conn:
            self._attributes.pop(name)
            del conn 
            return True 
        return False

    #- Plugins/Metadata ----
    @property
    def plugin_file(self):
        """
        Returns the plugin file associated with this node type.

        returns:
            (str) - plugin filename.
        """
        import inspect
        src_file = inspect.getfile(self.__class__)
        if os.path.exists(src_file.rstrip('c')):
            plugin_file = src_file.rstrip('c')
        return plugin_file
    
    @property
    def is_builtin(self):
        """
        Returns true if the node is a member for the is_builtin 
        plugins.

        returns:
            (bool)  - plugin is a builtin.
        """
        return SCENEGRAPH_PLUGIN_PATH in self.plugin_file

    def parse_metadata(self):
        """
        Initialize node metadata from metadata files on disk.
        Metadata is parsed by looking at the __bases__ of each node
        class (ie: all DagNode subclasses will inherit all of the default
        DagNode attributes).
        """
        import inspect
        from . import metadata
        parser = metadata.MetadataParser()

        node_metadata = dict()

        # query the base classes
        result = [self.__class__,]
        for pc in self.ParentClasses():
            result.append(pc)
        
        sg_core_path = os.path.join(SCENEGRAPH_PATH, 'core', 'nodes.py')

        for cls in reversed(result):
            cname = cls.__name__
            src_file = inspect.getfile(cls)
            py_src = src_file.rstrip('c')

            dirname = os.path.dirname(src_file)
            basename = os.path.splitext(os.path.basename(src_file))[0]
            
            # return the source .py file if it exists
            if os.path.exists(py_src):
                src_file = py_src

            metadata_filename = os.path.join(dirname, '%s.mtd' % basename)

            # default DagNode type is special.
            if py_src == sg_core_path:
                metadata_filename = os.path.join(SCENEGRAPH_PLUGIN_PATH, 'dagnode.mtd')
            
            if not os.path.exists(metadata_filename):
                raise OSError('plugin description file "%s" does not exist.' % metadata_filename)

            parsed = parser.parse(metadata_filename)

            for section in parsed:
                if section not in node_metadata:
                    node_metadata[section] = dict()

                attributes = parsed.get(section)
                    
                # parse out input/output here?
                for attr in attributes:
                    if attr not in node_metadata[section]:
                        node_metadata.get(section)[attr] = dict()
                    else:
                        pass
                        #log.debug('METADATA: module "%s" updating attribute: "%s:%s"...' % (basename, section, attr))

                    attr_properties = attributes.get(attr)
                    for pname in attr_properties:
                        pvalues = attr_properties.get(pname)

                        if pname not in node_metadata.get(section).get(attr):
                            node_metadata.get(section).get(attr)[pname] = dict()
                        else:
                            pass
                            #log.debug('METADATA: module "%s" updating attribute property: "%s:%s:%s"...' % (basename, section, attr, pname))
                        
                        if util.is_dict(pvalues):
                            for pattr in pvalues:
                                pval = pvalues.get(pattr)
                                node_metadata.get(section).get(attr)[pname] = pval
                        else:
                            # "output:value:connectable":  True
                            node_metadata.get(section).get(attr)[pname] = pvalues
                            #print '# "%s:%s:%s": ' % (attr, pattr, pname), pvalues


            node_metadata
        return node_metadata

    def Class(self):
        return self.__class__.__name__

    def dag_types(self):
        return [c.__name__ for c in DagNode.__subclasses__()]

    def ParentClasses(self, p=None):
        """
        Returns all of this objects' parent classes.
        params:
            p (obj) - parent class.
        returns:
            (list) - list of parent class names.
        """
        base_classes = []
        cl = p if p is not None else self.__class__
        for b in cl.__bases__:
            if b.__name__ not in ["object", "Observable"]:
                base_classes.append(b)
                base_classes.extend(self.ParentClasses(b))
        return base_classes



#- Metadata -----

class Metadata(object):

    def __init__(self, parent=None, **kwargs):

        self._parent         = parent
        self._data           = dict()
        self._default_xform  = "Node Transform"
        self._default_attrs  = "Node Attributes" 
        self._template_data  = dict()               # dictionary to hold parsed data

        self._data.update(**kwargs)

    def __str__(self):
        return json.dumps(self.data, default=lambda obj: obj.data, indent=4)

    def __repr__(self):
        pc = self._parent.ParentClasses()
        parents = [x.__name__ for x in pc]
        parents.append(self._parent.Class())
        return 'Metadata: [%s]' % ','.join(parents)
        #return json.dumps(self.data, default=lambda obj: obj.data, indent=4)

    def update(self, data):
        """
        Update the data dictionary.

        * todo: can't pass as **kwargs else we lose the order (why is that?)
        """
        self._template_data = data
        for k, v in data.iteritems():
            if k in self._data:
                self._data.get(k).update(**v)
            else:
                self._data.update({k:v})

    def map(self, name, properties):
        """
        Maps data dictionary to an Attribute. Example:

            "shader_mapping": {
                "default": {
                    "type": "FILE",
                    "value": ""
                },
                "label": {
                    "type": "STRING",
                    "value": "Mapping"
                },
                "desc": {
                    "type": "STRING",
                    "value": "shaders mapping file."
                },
                "connection_type": {
                    "type": "INPUT",
                    "value": "file"
                }

        params:
            name       (str)  - attribute name.
            properties (dict) - attribute dictionary.
        """
        if not 'default' in properties:
            lof.error('attribute "%s" metadata is missing required "default" property.' % name)
            return 


        default_value = None

        # connection properties
        connectable = properties.pop('connectable')
        connection_type = properties.pop('connection_type')        
        max_connections = properties.pop('max_connections', 1) 

        pdict = dict()
        # attribute properties (ie 'label', 'desc', 'connection_type')
        for property_name in properties:

            pattrs = properties.get(property_name)
            if not util.is_dict(pattrs):
                continue

            property_value = pattrs.get('value')
            property_type  = pattrs.get('type')

            attr_type      = None

            if property_value:
                if property_value.isupper():
                    pass

                if property_type.isupper():
                    if property_type not in PROPERTY_TYPES.get('data_types'): 
                            attr_type = property_type.lower()
                    else:
                        # data type (ie 'FILE')
                        attr_type = property_type.lower()

            # {'label': 'Name'}
            pdict[property_name] = property_value
            pdict['attr_type'] = attr_type

        return self._parent.add_attr(name, connectable=True, connection_type=connection_type, 
                            max_connections=max_connections, default_value=default_value, user=False, **pdict)

    @property
    def data(self):
        return self._data

    def parentItem(self):
        """
        Returns the parent DagNode.

        returns:
            (DagNode) - parent DagNode.
        """
        return self._parent

    def clear(self):
        """
        Clears the parsed metadata.
        """
        self._data = dict()

    def sections(self):
        """
        Returns the metadata "sections" (top-level groups).

        returns:
            (list) - list of metadata group sections.
        """
        return self._data.keys()

    def attributes(self, section):
        """
        Returns the metadata attributes in a given section.

        returns:
            (list) - list of metadata attribute names.
        """
        if section in self.sections():
            return self._data.get(section).keys()
        return []

    def getAttr(self, section, attr):
        """
        Returns a metadata attribute.

        returns:
            (dict) - attribute dictionary.
        """
        if attr in self.attributes(section):
            return self._data.get(section).get(attr)
        return dict()

    def defaults(self):
        """
        Returns default node attributes.

        returns:
            (dict) - attributes dictionary.
        """
        if self._default_attrs is None:
            return dict()

        if self._default_attrs in self._data.keys():
            return self._data.get(self._default_attrs)
        return dict()

    def transformAttrs(self):
        """
        Returns default transform attributes.

        returns:
            (dict) - attributes dictionary.
        """
        if self._default_xform is None:
            return {}
        if self._default_xform in self._data.keys():
            return self._data.get(self._default_xform)
        return dict()

    def get_connection(self, name):
        return dict()

    def input_connections(self):
        """
        Parse the metadata and return input connections.

        returns:
            (list) - list of connection dictionaries.
                     * todo: should we return an attribute object here?
        """
        connections = []
        for section in self.sections():
            for attribute in self.attributes(section):
                attr_data = self.getAttr(section, attribute)

                if 'connection_type' in attr_data:
                    connectable = attr_data.get('connectable')
                    conn_type = attr_data.get('connection_type')

                    if conn_type == 'INPUT':
                        if connectable:
                            #connections.append({attribute:{'type':conn_type}})
                            connections.append({attribute:attr_data})
        return connections

    def output_connections(self):
        """
        Parse the metadata and return output connections.

        returns:
            (list) - list of connection dictionaries.
                     * todo: should we return an attribute object here?
        """
        connections = []
        for section in self.sections():
            for attribute in self.attributes(section):
                attr_data = self.getAttr(section, attribute)

                if 'connection_type' in attr_data:
                    connectable = attr_data.get('connectable')
                    conn_type = attr_data.get('connection_type')
                    
                    if conn_type == 'OUTPUT':
                        if connectable:
                            #connections.append({attribute:{'type':conn_type}})
                            connections.append({attribute:attr_data})
        return connections




'''
    def ParentClasses(self, p=None):
        """
        Returns all of this objects' parent classes.

        params:
            p (obj) - parent class.

        returns:
            (list) - list of parent class names.
        """
        base_classes = []
        cl = p if p is not None else self.__class__
        for b in cl.__bases__:
            if b.__name__ not in ["object", "Observable"]:
                base_classes.append(b)
                base_classes.extend(self.ParentClasses(b))
        return base_classes
'''