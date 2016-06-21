import os
import urllib2
import urlparse
import tempfile
import shutil
import Pyro4

from iso import Iso
from mcvirt.rpc.pyro_object import PyroObject

class Factory(PyroObject):
    """Class for obtaining ISO objects"""

    def __init__(self, mcvirt_instance):
        """Create object, storing MCVirt instance"""
        self.mcvirt_instance = mcvirt_instance

    def getIsos(self):
        """Returns a list of a ISOs"""
        # Get files in ISO directory
        file_list = os.listdir(self.mcvirt_instance.ISO_STORAGE_DIR)
        iso_list = []

        for iso_name in file_list:
            iso_path = os.path.join(self.mcvirt_instance.ISO_STORAGE_DIR, iso_name)
            if os.path.isfile(iso_path):
                iso_list.append(iso_name)
        return iso_list

    @Pyro4.expose()
    def getIsoByName(self, iso_name):
        """Creates and registers Iso object"""
        iso_object = Iso(self.mcvirt_instance, iso_name)
        self._register_object(iso_object)
        return iso_object

    @Pyro4.expose()
    def getIsoList(self):
        """Return a user-readable list of ISOs"""
        iso_list = self.getIsos()
        if len(iso_list) == 0:
            return 'No ISOs found'
        else:
            return "\n".join(iso_list)

    def addIso(self, path):
        """Copy an ISO to ISOs directory"""
        # Check that file exists
        if not os.path.isfile(path):
            raise InvalidISOPathException('Error: \'%s\' is not a file or does not exist' % path)

        filename = Iso.getFilenameFromPath(path)
        Iso.overwriteCheck(self.mcvirt_instance, filename,
                           self.mcvirt_instance.ISO_STORAGE_DIR + '/' + filename)

        shutil.copy(path, self.mcvirt_instance.ISO_STORAGE_DIR)
        full_path = self.mcvirt_instance.ISO_STORAGE_DIR + '/' + filename

        return self.getIsoByName(filename)

    @Pyro4.expose()
    def addFromUrl(url, name=None):
        """Download an ISO from given URL and save in ISO directory"""
        # Work out name from URL if name is not supplied
        if name is None:
            # Parse URL to get path part
            url_parse = urlparse.urlparse(url)
            name = Iso.getFilenameFromPath(url_parse.path)

        # Get temporary directory to store ISO
        temp_directory = tempfile.mkdtemp()
        output_path = temp_directory + '/' + name

        # Open file
        iso = urllib2.urlopen(url)

        # Read file in 16KB chunks
        chunk_size = 16 * 1024

        # Save ISO
        with open(output_path, 'wb') as file:
            while True:
                chunk = iso.read(chunk_size)
                if not chunk:
                    break
                file.write(chunk)
        iso.close()

        iso_object = self.addIso(output_path)

        os.remove(output_path)
        os.rmdir(temp_directory)
        self._register_object(iso_object)
        return iso_object
