#!/usr/bin/env python
import os

PACKAGE                     = 'SceneGraph'
VERSION                     = 0.55
REVISION                    = 3
VERSION_AS_STRING           = '%.02f.%d' % (VERSION, REVISION)

SCENEGRAPH_PATH             = os.path.dirname(__file__)
SCENEGRAPH_NODE_PATH        = os.path.join(SCENEGRAPH_PATH, 'core', 'dagnodes')
SCENEGRAPH_UI               = os.path.join(SCENEGRAPH_PATH, 'ui', 'SceneGraph.ui')
SCENEGRAPH_ATTR_EDITOR_UI   = os.path.join(SCENEGRAPH_PATH, 'ui', 'designer', 'NodeAttributes.ui')
SCENEGRAPH_ICON_PATH        = os.path.join(SCENEGRAPH_PATH, 'icn')
SCENEGRAPH_STYLESHEET_PATH  = os.path.join(SCENEGRAPH_PATH, 'css')
SCENEGRAPH_PREFS_PATH       = os.path.join(os.getenv('HOME'), '.config', PACKAGE)
