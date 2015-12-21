bl_info = {
    "name": "Point Cloud Loader",
    "author": "Short Notion (Mark van de Korput)",
    "version": (0, 1),
    "blender": (2, 75, 0),
    "location": "View3D > T-panel > Object Tools",
    "description": "Generate point cloud from data files",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Add Mesh"}

# system stuff
import logging
# blender stuff
import bpy
from bpy.app.handlers import persistent
import bmesh
import os.path
import mathutils

# Scene updates
class PointCloudLoader:
  def __init__(self, scene=None):
    self.scene=scene
    
    if self.scene == None: # default to currently active scene
      self.scene = bpy.context.scene 

  # gives all objects in the scene for who the pointCloudLoaderConfig is enabled (through the panel)
  def enabledObjects(self):
    return [obj for obj in self.scene.objects if obj.pointCloudLoaderConfig.enabled == True]

  # loads the current frame for all point-cloud-enabled objects in the scene
  def loadFrame(self, force=False):
    objs = self.enabledObjects()
    print("Number of point cloud objects: {0}".format(len(objs)))

    # load point clouds for the current frame for all point-cloud-enabled objects in the scene
    for obj in objs:
      ObjectPointObjectLoader(obj, scene=self.scene, force=force).loadFrame()
# end of class PointCloudLoader


# Object updater
class ObjectPointObjectLoader:
  def __init__(self, obj, scene=None, force=False):
    self.obj = obj
    self.config = obj.pointCloudLoaderConfig
    self.force=force

    self.scene=scene
    if self.scene == None: # default to currently active scene
      self.scene = bpy.context.scene 

  # load point cloud for the current frame for the specified object
  def loadFrame(self):
    print("Loading point cloud for object: " + self.obj.name)

    # get file path, create file parser instance
    path = ObjectFileManager(self.obj).frameFilePath(self.scene.frame_current)
    if path == None:
      print("Couldn't find point cloud frame file, aborting")
      return

    if self.force != True and self.config.currentFrameLoaded == path:
      print("Current point cloud frame already loaded, aborting")
      return

    file = PointCloudFrameFile(path=path, skip=self.config.skipPoints)
    if self.config.bounds == True:
      file.minBounds = self.config.boundsMin
      file.maxBounds = self.config.boundsMax

    if self.config.modify:
      file.offset = self.config.vertOffset
      file.multiply = self.config.vertMultiply

    # create mesh generator instance, feed it the points form the file parser
    pcofl = PointCloudObjectFrameLoader(self.obj, file.get_points(), scene=self.scene)
    
    if self.obj.pointCloudLoaderConfig.skin == True:
      pcofl.removeExisting()
      
    # pcofl.removeFaces()

    pcofl.createPoints()
    # "skin" the mesh if the skin flag is enabled
    if self.obj.pointCloudLoaderConfig.skin == True:
      self._skinObject(pcofl.getContainerObject())

      if self.config.materialName != None and self.config.materialName != '':
        materialiser = PointCloudMeshMaterialiser(obj=pcofl.getContainerObject(), materialName=self.config.materialName)
        materialiser.applyMaterial()

    # done, store the path to the point-cloud-data file in the object's config, so
    # we know we don't have to load it again if the same file is specified
    self.obj.pointCloudLoaderConfig.currentFrameLoaded = path

  def removeExisting(self):
    PointCloudObjectFrameLoader(self.obj, scene=self.scene).removeExisting()

  def canSkin(self):
    return hasattr(self.scene, 'CONFIG_PointCloudSkinner')

  def _skinObject(self, obj):
    if self.canSkin() != True:
      print("Can't skin point cloud mesh; scene doesn't have CONFIG_PointCloudSkinner attribute. ")
      print("Please install and enable Point Cloud Skinner addon. See http://sourceforge.net/projects/pointcloudskin/")
      return

    print("Skinning mesh")

    originalSkinObject = self.scene.CONFIG_PointCloudSkinner.target_object # remember for later restore
    self.scene.CONFIG_PointCloudSkinner.target_object = obj.name
    bpy.ops.scene.point_cloud_skinner_skin()
    self.scene.CONFIG_PointCloudSkinner.target_object = originalSkinObject # restore
# end of class ObjectPointObjectLoader


# manages point-cloud data frame files
class ObjectFileManager:
  def __init__(self, obj):
    self.obj = obj
    self.config = obj.pointCloudLoaderConfig

  def getPointCloudFrameNumber(self, sceneFrameNumber):
    # first see if they pointCloudFrame config property
    # is set to a valid point cloud frame number, if so, return that
    if self.config.pointCloudFrame != -1:
      return self.config.pointCloudFrame

    total = self.numberOfFiles()
    if total == 0:
      return None

    # calculate the PC data frame number using the frameRatio config property
    return int(sceneFrameNumber*self.config.frameRatio) % total

  # returns the file path of the file that contains
  # the point-cloud data for the specified scene frame
  def frameFilePath(self, sceneFrameNumber):
    fnumber = self.getPointCloudFrameNumber(sceneFrameNumber)
    return self.pathForPointCloudFrame(fnumber)

  # turns a point cloud frame number into a frame file path
  def pathForPointCloudFrame(self, pointCloudFrameNumber):
    if pointCloudFrameNumber == None:
      return None

    path = self.config.fileName % pointCloudFrameNumber

    if path.startswith("/"): # absolute path?
      return path
    return bpy.path.abspath("//"+path) # relative path (must be relative to blender file)

  def numberOfFiles(self):
    if self.config and self.config.numFiles > 0:
      return self.config.numFiles

    return self.autoNumberOfFiles()

  # this method tries to determine the number of point cloud files automatically
  def autoNumberOfFiles(self):
    if hasattr(self, 'autoNumberOfFiles_cache'):
      return self.autoNumberOfFiles_cache

    minN = 0
    maxN = 0

    while os.path.isfile(self.pathForPointCloudFrame(maxN)):
      maxN+=1

    self.autoNumberOfFiles_cache = maxN - minN
    print("ObjectFileManager#autoNumberOfFiles - number of files detected: {0}".format(self.autoNumberOfFiles_cache))
    return self.autoNumberOfFiles_cache
# end  of class ObjectFileManager


# This class performas the actual mesh operations
# (creating/removing/updating vertices and faces)
class PointCloudObjectFrameLoader:
  def __init__(self, obj, points = [], scene=None):
    self.obj = obj
    self.points = points
    self.scene = scene

    if self.scene == None:
      self.scene = bpy.context.scene

  def _existingMesh(self):
    obj = self._existingContainerObject()
    if obj == None:
      print("Couldn't find existing container object")
      return None
    print("Found existing pointcloud mesh")
    return obj.data

  def _createMesh(self):
    print("Creating new pointcloud mesh")
    return bpy.data.meshes.new("pointscloudmesh")

  def getMesh(self):
    # this find existing container object,
    # or creates one. In both cases, it returns a container object with mesh data
    return self.getContainerObject().data

  def _existingContainerObject(self):
    # find first child whose name start with "pointcloud" and has mesh data
    for child in self.obj.children:
      if child.name.startswith("pointcloud") and child.data != None:
        print("Found existing pointcloud container object")
        return child

    return None

  def _createContainerObject(self): # uncached
    print("creating pointcloud container object")
    cobj = bpy.data.objects.new("pointcloud", self._createMesh())
    cobj.parent = self.obj
    # cobj.show_x_ray = True
    self.scene.objects.link(cobj)
    return cobj

  # ty to get existing object, otherwise create one
  def getContainerObject(self):
    return self._existingContainerObject() or self._createContainerObject()

  # this function does a lot of trickery to get some vertices removed from the pointcloudmesh
  # it's emabrassing how convoluted blender logic is; it's MVC gone all wrong and reverse
  def _removeVertices(self, containerObj, count):
    print("Removing {0} vertices from pointcloud mesh".format(count))
    mesh = containerObj.data

    originalActive = self.scene.objects.active # remember currently active object, so we can restore at the end of this function
    self.scene.objects.active = containerObj # make specified object the active object

    bpy.ops.object.mode_set(mode="EDIT")  # endter edit mode just for a deselect all
    bpy.ops.mesh.select_all(action = 'DESELECT')
    # bpy.ops.object.mode_set(mode="OBJECT")  # return to object mode

    # select vertices for removal
    for i in reversed(range(len(mesh.vertices) - count, len(mesh.vertices))):
      mesh.vertices[i].select = True

    # go back into edit mode to delete
    # bpy.ops.object.mode_set(mode = 'EDIT')
    bpy.ops.mesh.delete()
    bpy.ops.object.editmode_toggle() # back to OBJECT mode
    self.scene.objects.active = originalActive

  def removeExisting(self):
    print("Removing existing point cloud mesh and container object")
    containerObject = self._existingContainerObject()
    if containerObject != None:
      self.scene.objects.unlink(containerObject)
      bpy.data.objects.remove(containerObject)

  # the removeFaces function isn't working... can't figure it out
  def removeFaces(self):
    containerObj = self.getContainerObject()
    mesh = self.getMesh()
    print("Removing all faces from mesh: "+mesh.name)
    
    originalActive = self.scene.objects.active # remember currently active object, so we can restore at the end of this function
    self.scene.objects.active = containerObj # make specified object the active object

    # Get a BMesh representation
    # bm = bmesh.from_edit_mesh(mesh)
    bm = bmesh.new()
    bm.from_mesh(mesh)

    bpy.ops.object.mode_set(mode="EDIT")  # endter edit mode just for a deselect all
    bpy.ops.mesh.select_all() #action='TOGGLE')
    containerObj.select = True
    bpy.ops.mesh.delete() #type='FACE')
    # bmesh.update_edit_mesh(mesh, True)
    bpy.ops.object.editmode_toggle() # back to OBJECT mode
    bm.to_mesh(mesh)
    bm.free()
    self.scene.objects.active = originalActive

  def createPoints(self):
    print("Creating point cloud for object: "+self.obj.name)
    # find existing mesh or creates a new one (inside a "pointcloud" container object)
    mesh = self.getMesh()
    config = self.obj.pointCloudLoaderConfig

    # first make sure the mesh has exactly the right amount of vertices
    existingVertexCount = len(mesh.vertices.values())

    if existingVertexCount < len(self.points):
      print("Adding {0} vertices to pointcloud mesh".format(len(self.points) - existingVertexCount))
      # add missing vertices
      mesh.vertices.add(len(self.points) - existingVertexCount)
    else:
      # remove any surplus vertices
      self._removeVertices(self.getContainerObject(), existingVertexCount - len(self.points))

    # initialize all vertices of the mesh
    idx = 0
    for point in self.points:
      mesh.vertices[idx].co = (point[0], point[1], point[2])
      idx += 1

    self.scene.update()
# end of class PointCloudObjectFrameLoader

# this class applies a specified existing material to a specified existing object
class PointCloudMeshMaterialiser:
  def __init__(self, obj=None, materialName=None):
    self.obj = obj
    self.materialName = materialName

  def applyMaterial(self):
    print("Applying material {0} to object {1}".format(self.materialName, self.obj.name))

    materialIdx = bpy.data.materials.find(self.materialName)

    if materialIdx == -1:
      print("Material not found, aborting")
      return

    self.obj.data.materials.append(bpy.data.materials[materialIdx])

# A class that represents one file (frame) of piont cloud data,
# this class takes care of parsing the file's data into python data (arrays)
class PointCloudFrameFile:
  def __init__(self, path, skip=0, logger=None, minBounds=None, maxBounds=None, offset=None, multiply=None):
    self.path = path
    self.logger = logger
    self.minBounds = minBounds
    self.maxBounds = maxBounds
    self.offset = offset
    self.multiply = multiply

    self.skip = skip # after every read point, skip this number of points
    self.points = [] # for the points defined in the file
    self.all_points = [] # for all points; also the non-active ones
    self.rejected_points = [] # for all points which are reject because of ouf enforced bounds

    if self.logger == None:
      self.logger = logging # default logging object from the imported logging module

  def get_all_points():
    if len(self.all_points) == 0:
      self._loadFrameData()
    return self.all_points

  def get_points(self):
    if len(self.points) == 0:
      self._loadFrameData()
    return self.points

  def _loadFrameData(self):
    print("Loading point cloud frame file: " + self.path)
    f = open(self.path)

    while f:
      line = f.readline()
      try: 
        idx,x,y,z = [100*float(v) for v in line.split(",")]
        reject = False
        # idx = int(idx)

        v = list((x,y,z)) #Vector(x,y,z) #c4d.Vector(x,y,z) # turn coordinates into c4d Vector object

        if self.multiply != None:
          for i in range(3):
            v[i] = v[i] * self.multiply[i]

        if self.offset != None:
          for i in range(3):
            v[i] += self.offset[i]

        if self.minBounds != None:
          for i in range(3):
            if v[i] < self.minBounds[i]:
              reject = True
              break

        if reject != True and self.maxBounds != None:
          for i in range(3):
            if v[i] > self.maxBounds[i]:
              reject = True
              break

        v = (v[0], v[1], v[2]) # convert from list to immutable tuple
        self.all_points.append(v) # add the vector to our list

        # create selection of relevant (non-zero) points
        if reject == True:
          self.rejected_points.append(v)
        else:
          if x*y*z != 0:
            self.points.append(v)

      except ValueError:
        break

      # skip some points (if skip > 0)
      for i in range(self.skip):
        f.readline()

    f.close()
    print('PointCloudFrameFile#_loadFrameData - points read (total/active): {0}/{1}'.format(str(len(self.all_points)), str(len(self.points))))
# end of class PointCloudFrameFile


# This class is in charge of the blender UI panel
class PointCloudLoaderPanel(bpy.types.Panel):
    """Creates a Point Cloud Loader Panel in the Object properties window"""
    bl_label = "Point Cloud Loader"
    bl_idname = "OBJECT_PT_point_cloud_loader"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw_header(self, context):
      layout = self.layout
      config = context.object.pointCloudLoaderConfig
      layout.prop(config, "enabled", text='')

    def draw(self, context):
        layout = self.layout
        config = context.object.pointCloudLoaderConfig

        if config.enabled == True:
          layout.row().prop(config, "fileName")
          layout.row().prop(config, "skipPoints")
          layout.row().prop(config, "numFiles")

          if config.numFiles == 0:
            layout.row().label(text="Number of files will be auto-detected at runtime")

          layout.row().operator("object.set_pointcloud_animation_length", text="Set animation length")
          layout.row().prop(config, "frameRatio")
          layout.row().prop(config, "pointCloudFrame")

          layout.row().prop(config, "skin")
          layout.row().prop(config, "materialName")

          if config.skin == True:
            if ObjectPointObjectLoader(context.object).canSkin() != True:
              layout.row().label(text="!! Please install/enable Point Cloud Skinner addon !!")

          layout.row().prop(config, 'modify', text="Vertex load-time modifiers")

          if config.modify == True:
            layout.row().prop(config, 'vertMultiply')
            layout.row().prop(config, 'vertOffset')

          layout.row().prop(config, 'bounds', text="Enforce vertex bounds at load-time")
          if config.bounds == True:
            layout.row().prop(config, 'boundsMin')
            layout.row().prop(config, 'boundsMax')

          layout.row().operator("object.reload_point_cloud", text="Reload point cloud")
          layout.row().operator("object.load_point_cloud", text="Load point cloud now")

        layout.row().operator("object.remove_point_cloud", text="Remove point cloud")
# end of class PointCloudLoaderPanel


# This class represents the config data (that the UI Panel interacts with)
class PointCloudLoaderConfig(bpy.types.PropertyGroup):
  @classmethod
  def register(cls):
    bpy.types.Object.pointCloudLoaderConfig = bpy.props.PointerProperty(
      name="Point Cloud Loader Config",
      description="Object-specific Point Cloud Loader properties",
      type=cls)
   
    # Add in the properties
    cls.enabled = bpy.props.BoolProperty(name="enabled", default=False, description="Enable point cloud for this object")
    cls.fileName = bpy.props.StringProperty(name="Data Files", default="pointCloudData/frame%d.txt")
    cls.skipPoints = bpy.props.IntProperty(name="Skip Points", default=0, soft_min=0)
    cls.numFiles = bpy.props.IntProperty(name="Number of files", default=100, soft_min=0)
    cls.frameRatio = bpy.props.FloatProperty(name="Frame ratio", default=1.0, soft_min=0.0, description="Point cloud frame / blender frame ratio")
    cls.pointCloudFrame = bpy.props.IntProperty(name="Current Point Cloud Data Frame", default=-1, soft_min=-1, description="Key-frameable property to specify which ppoint cloud data frame to use. When -1, it will be ignored, and the frameRatio will be used to calculate the current point cloud data from from the current scene frame.")

    cls.skin = bpy.props.BoolProperty(name="skin", default=False, description="Skin point cloud mesh using, Point Cloud Skinner addon")
    cls.materialName = bpy.props.StringProperty(name="Material name", default="")

    cls.modify = bpy.props.BoolProperty(name="modify", default=False, description="Modify point cloud vertices at load time")
    try:
      cls.vertOffset = bpy.props.FloatVectorProperty(name="Vertex Offset", description="The position of all vertices is offset with this vector at load-time", default=(1.0, 1.0, 1.0))
      cls.vertMultiply = bpy.props.FloatVectorProperty(name="Vertex Multiply", description="The position of all vertices is multiplied by this vector at load-time", default=(1.0, 1.0, 1.0))
    except: #(ValueError, AttributeError, NameError):
      pass

    cls.bounds = bpy.props.BoolProperty(name="bounds", default=False, description="Apply bounding box that rejects vertices at load time")
    try:
      cls.boundsMin = bpy.props.FloatVectorProperty(name="Bounds minimum vector", default=(-10.0, -10.0, -10.0))
      cls.boundsMax = bpy.props.FloatVectorProperty(name="Bounds maximum vector", default=(10.0, 10.0, 10.0))
    except:
      pass
    # not configurable; for internal use (optimilization)
    cls.currentFrameLoaded = bpy.props.StringProperty(name="Currently Loaded Frame File", default="")

  ## Unregister is causing errors and doesn't seem to be necessary
  # @classmethod
  # def unregister(cls):
  #   print("Unreg: ")
  #   print(dir(bpy.types.Object))
  #   del bpy.types.Object.pointCloudLoaderConfig
# end of class PointCloudLoaderConfig


# Operation classes
class PointCloudLoaderLoadOperator(bpy.types.Operator):
    bl_idname = "object.load_point_cloud"
    bl_label = "Load a point cloud (Point Cloud Loader)"
    bl_description = "Load point cloud data from external files."

    # @classmethod
    # def poll(cls, context):
    #     return True

    def execute(self, context):
      obj = context.object
      if obj.pointCloudLoaderConfig.enabled == True:
        ObjectPointObjectLoader(obj, force=True).loadFrame()
      return {'FINISHED'}

class PointCloudLoaderRemoveOperator(bpy.types.Operator):
    bl_idname = "object.remove_point_cloud"
    bl_label = "Remove point cloud (Point Cloud Loader)"
    bl_description = "Remove loaded point cloud mesh"

    # @classmethod
    # def poll(cls, context):
    #     return True

    def execute(self, context):
      obj = context.object
      if obj.pointCloudLoaderConfig.enabled == True:
        ObjectPointObjectLoader(obj, force=True).removeExisting()
      return {'FINISHED'}

class PointCloudLoaderReloadOperator(bpy.types.Operator):
    bl_idname = "object.reload_point_cloud"
    bl_label = "Remove point cloud (Point Cloud Loader)"
    bl_description = "Remove loaded point cloud mesh"

    # @classmethod
    # def poll(cls, context):
    #     return True

    def execute(self, context):
      bpy.ops.object.remove_point_cloud()
      bpy.ops.object.load_point_cloud()
      return {'FINISHED'}

class PointCloudLoaderSetPointcloudAnimationLengthOperator(bpy.types.Operator):
    bl_idname = "object.set_pointcloud_animation_length"
    bl_label = "Set animation length based on point cloud data length (Point Cloud Loader)"
    bl_description = "Make blender's render animation length fit the number of point cloud data frames."

    # @classmethod
    # def poll(cls, context):
    #     return True

    def execute(self, context):
      context.scene.frame_start = 0
      context.scene.frame_end = ObjectFileManager(context.object).numberOfFiles()-1
      return {'FINISHED'}
      

# Blender addon stuff, (un-)registerers and events handlers
@persistent
def frameHandler(scene):
  print("-- PointCloudLoader frame update START --")
  PointCloudLoader(scene=scene).loadFrame()
  print("-- PointCloudLoader frame update END --")

def register():
  bpy.utils.register_module(__name__)
  bpy.app.handlers.frame_change_pre.append(frameHandler)

def unregister():
  bpy.utils.unregister_module(__name__)
  bpy.app.handlers.frame_change_pre.remove(frameHandler)

if __name__ == "__main__":
  register()
