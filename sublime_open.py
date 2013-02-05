from functools import partial
from collections import defaultdict, namedtuple
import os

import sublime_plugin
import sublime

#How many files do we want to keep in our history
number_of_recent_files = 500

#put this in front of directories to make it easy to filter for directories
directory_prefix = '`'
#define the paths to where we store our collections
#you can add more collections just remeber to update your keymap
collections = {
    'favorites': os.path.join(os.getcwd(), 'collections', 'favorites_%s.txt'),
    'recent': os.path.join(os.getcwd(), 'collections', 'recent_%s.txt'),
    'projects': os.path.join(os.getcwd(), 'collections', 'projects.txt')
}

#how much of the filepath do you want to show 
file_path_depth = {
    'default': 3,
    #define per collection
    'favorites': 4,
    'recent': 0
}

#store path here for persistence's sake
path = ''


def get_change_dir_string(path):
    '''Return a formatted CD string

        Given a path this function returns a string of the form
        /path/to/(parent)/current

    '''
    path, file_name = os.path.split(path)
    if path and file_name:
        tail, head = os.path.split(path)
        if head:
            return os.path.join(tail, "(%s)" % head, file_name) 
        else:
            return os.path.join("(%s)" % path.strip('\\/'), file_name) 
    else:
        return 'Home Directory (%s)' % path

class SublimeException(Exception):
    def __init__(self, message):
        sublime.status_message(message)

#don't list files with these extensions (except in collections)
excluded_extensions = [
    '.pyc',
    '.png',
    '.jpg'
]

#A reuseable functions to read files paths from a text file.
#If the text file does not exists we create it and return an empty list.
def get_list_from_file(file_name, count = -1):
    output = []
    try:
        with open(file_name) as collection:
            for path in collection.readlines():
                output.append(path.strip())
                count -= 1
                if count == 0:
                    break
    except IOError:
        #create the file if it didn't exist
        with open(file_name, 'w') as f:
            pass

    return output

def write_list_to_file(input, file_path):
    #write a list to a file, one element per line
    with open(file_path, 'w') as output:
        output.write('\n'.join(input))

def valid_file(path):
    for extension in excluded_extensions:
        if path.endswith(extension):
            return False
    return True

def create_project(input):
    p = namedtuple('Project', ['name', 'match'])
    data = [x.strip() for x in input.split(':')]
    name = data.pop(0).strip()
    match = data.pop() if data else ''
    return p(name, match)


def init_projects():
    projects = [create_project(x) for x in get_list_from_file(collections['projects'])]

    current_project = projects[0] if projects else 'default'
    return projects, current_project

#we get the last project that we had open
#This must be stored as a global so that when we close/open/favorite a new file
#it is added to the correct 'recent' collection
projects, current_project = init_projects();

class FindCommand(sublime_plugin.TextCommand):
    def run(self, edit, command = 'open', collection = False):
        self.window = sublime.active_window()
        self.file_name = self.view.file_name()

        #if no filename then we use the path from the previous file
        self.path = os.path.dirname(self.file_name or path)

        if not ( self.path or collection ):
            raise SublimeException("Error no path found!")

        if 1:
            return {
                'new_file': self.file_prompt,
                'new_directory': self.directory_prompt,
                'delete_file': self.delete_file,
                'show_collection': partial(self.show_collection, collection),
                'project': self.show_projects,
                'open': partial(self.change_directory, self.path)
            }[command]()

        else:
            raise SublimeException("Invalid Command!")

    #List all files/directories in the current directory.
    def list_files(self):
        '''
            Show all non excluded files located in the directory self.path

            We don't just show the raw file name we show:
               1. Special Commands (cd, new file, etc)
               2. For Search we display
                    File:
                       File Name
                       Shortened Path
                    Directory:
                        <directory_prefix>Directory Name
                        Shortened Path
        '''
        
        common_commands = [
            ['Change Directory', get_change_dir_string(self.path)], 
            ['Other Options', 'New File/Folder | Recent/Favorites | Switch Project']
        ]

        file_names = [f for f in os.listdir(self.path) if valid_file(f)]
        self.files = [os.path.join(self.path, f) for f in file_names]
        display_names = create_display_names(self.files, file_path_depth['default'])
        
        self.window.show_quick_panel(common_commands + display_names, self.handle_input)
    
    #Call back function after the user select what file/command to open
    def handle_input(self, command):
        if command == -1:
            return #nothing selected do nothing
        elif command < 2:
            return [
                self.go_back_directory,
                self.custom_commands
            ][command]() #call the appropriate command based on index
        
        #they selected a file so we grab its path
        path = self.files[command - 2] 
        self.open_path(path)

    def custom_commands(self, command = None):
        if command is None:
            return self.window.show_quick_panel([
                ['Back To Files', 'View Files in Current Directory'],
                ['New File', 'Create a new file'], 
                ['New Folder', 'Create a new folder'], 
                ['Recent Files', 'View recent files'], 
                ['Favorite Files/Folders', 'View favorite files'],
                ['Switch Project', 'Switch Between Projects']
            ], self.custom_commands)
            

        if command == -1:
            return #nothing selected do nothing

        return [
            self.list_files,
            self.file_prompt,
            self.directory_prompt,
            partial(self.show_collection, 'recent'),
            partial(self.show_collection, 'favorites'),
            self.show_projects
        ][command]()

    def show_projects(self):
        self.window.show_quick_panel(
            [['New Project', 'Create a New Project']] + [[p.name, p.match or 'Match Everything'] for p in projects], 
            self.change_project
        )

    def change_project(self, project_number):
        global current_project
        if project_number < 0:
            return
        if project_number == 0:
            self.create_project()
        else:
            current_project = projects[project_number - 1]
            projects.remove(current_project)
            projects.insert(0, current_project)
            self.update_projects()
            
        self.show_collection('recent')

    def create_project(self, response=None):
        global current_project
        if response == None:
            self.prompt("Create a New Project", self.create_project, '')
            return

        project = create_project(response)
        if project.name in [x.name for x in projects]:
            sublime.status_message(project.name + " is already a project")
        else:
            projects.insert(0, project)
            self.update_projects()
            current_project = project
            sublime.status_message("Project '%s' created!" % project.name)

    def update_projects(self):
        write_list_to_file(
            ["%s:%s" % (p.name, p.match) for p in projects],
            collections['projects']
        )

    def show_collection(self, collection):
        '''
            Show all files in one of our collections, favorites, recent, etc.

            We do some interesting stuff to the file paths to make them as short as
            possible without loosing the ability to effectively search them.

                1) If a file name is unique we show it in the form:
                    Filename
                    Shortend Path
                2) If there are multiple files with the same name we find the shortest
                    unique path for each file and display that in the form:
                    Filename [short unique path]
                    Shortened Path

            This allows you to refine your search in reverse order, instead of having to 
            back track.
        '''
        print current_project
        self.files = get_list_from_file(collections[collection] % current_project.name)
        search_names = [format_path_for_search(p) for p in get_unique_suffixes(self.files)]
        short_paths = [shorten_path(p, file_path_depth[collection]) for p in self.files]

        self.window.show_quick_panel(
            [[a, b] for a, b in zip(search_names, short_paths)],
            self.open_collection
        )

    def open_collection(self, file_number):
        if file_number < 0:
            return
        
        path = self.files[file_number]
        self.open_path(path)    

    def file_prompt(self):
        self.prompt("Create a New File", self.open_path)

    def open_path(self, path):
        if not path:
            return
        if os.path.isdir(path):
            self.change_directory(path)
        else:
            self.window.open_file(path)
    
    def delete_file(self, confirm = -1):
        if confirm == -1:
            self.prompt(
                "Delete File: %s [blank/\"no\" to cancel]" % self.file_name, 
                self.delete_file,
                ''
            )

        elif confirm.lower() == 'yes':
            if os.path.exists(self.file_name):
                os.remove(self.file_name)
            else:
                raise SublimeException("Path %s is not a file" % self.file_name)

    def directory_prompt(self):
        self.prompt("Create a New Directory", self.create_directory)

    def create_directory(self, path):
        if os.path.exists(path): 
            sublime.status_message(path + " already exists...")
        else:
            os.makedirs(path)
            sublime.status_message(path + " succesfully created...")
            
        self.change_directory(path)

    def prompt(self, title, follow, path = "default"):
        if path == "default":
            path = os.path.join(self.path, '') 

        self.window.show_input_panel(
            title, 
            path,
            follow, 
            None, 
            None
        )
    
    def go_back_directory(self):
        parent_path = os.path.split(self.path)[0]
        self.change_directory(parent_path)

    def change_directory(self, new_path):
        global path
        self.path = new_path
        path = self.path       
        self.list_files() 

#Add file path to recent everytime we open/close it
class RecentCommand(sublime_plugin.EventListener):
    def on_close(self, view):
        self.update_recent(view.file_name())
    
    def on_load(self, view):
        self.update_recent(view.file_name())
    
    def update_recent(self, file_name):
        collection_name = self.get_collection(file_name)
        if not file_name:
            return
        paths = get_list_from_file(collection_name, number_of_recent_files)
        recent = [path for path in paths if path.lower() != file_name.lower()]
        recent.insert(0, file_name)

        write_list_to_file(recent, collection_name)

    def get_collection(self, file_name):
        for project in projects:
            if project.match in file_name:
                project_name = project.name
                break
        else:
            project_name = 'default'
        return collections['recent'] % project_name

#Add curent file, or it's parent folder to Favorites
class FavoriteCommand(sublime_plugin.TextCommand):
    def run(self, edit, command = False):
        file_name = self.view.file_name()
        if not file_name:
            return
        if command == "parent_folder":
            file_name = os.path.dirname(file_name)
        self.add_to_favorites(file_name)

    def add_to_favorites(self, file_name):
        collection_name = collections['favorites'] % current_project
        favorites = get_list_from_file(collection_name)
        if file_name in favorites:
            sublime.status_message(file_name + " already in favorites...")
        else:
            favorites.insert(0, file_name)
            write_list_to_file(favorites, collection_name)
            sublime.status_message(file_name + " added to favorites...")

#shorten a file path to only show the lowest "depth" number of folders
#e.g. shorten_path('Z:\folder_a\folder_b\folder_c\folder_d\file.py', 2) => '..\folder_c\folder_d\file.py'
def shorten_path(path, depth = 2):
    '''
        Shorten file path

        shorten a file path to only show the lowest "depth" number of folders
        e.g. shorten_path('Z:\folder_a\folder_b\folder_c\folder_d\file.py', 2) => '..\folder_c\folder_d\file.py'
    '''
    if not depth: 
        return path

    tail, head = os.path.split(path)
    output = [head]
    for i in range(depth):
        tail, head = os.path.split(tail)
        if head:
            output.append(head)
        elif tail:
            output.append(tail)
        else:
            break
    else:
        output.append('..')         

    return  os.path.join(*reversed(output))

def create_display_names(paths, depth = 0):
    display_names = []
    for path in paths:
        #be able to quickly filter for directories, helpful if you are trying to walk the 
        #directory tree.  This could be slow in huge directories, it may be quicker to just
        #check for a file extension, it wouldn't be perfect, but it is probably good enough
        prefix = directory_prefix if os.path.isdir(path) else ""
        tail, file_name = os.path.split(path)
        display_names.append([prefix + (file_name or 'Home (%s)' % path), shorten_path(tail, depth)])

    return display_names

def get_unique_suffixes(paths):
    '''
        Find the shortest unique path to for every file in a list

        Given a list of file paths this reutnrs a list of the shortest
        unique suffix to represent each file, e.g.
            Input: a/b/c/foo.py, x/y/z/foo.py, a/b/z/foo.py
            Output c/foo.py, y/z/foo.py, b/z/foo.py
    '''
    p = [{'suffix': i, 'path': i} for i in set(paths)]

    suffixes = _get_unique_suffixes(p, '')

    path_map = dict((i[1], i[0]) for i in suffixes)
    return [path_map[path] or path for path in paths]

def _get_unique_suffixes(paths, end):
    output, suffixes = [], defaultdict(list)
    for path in paths:
        tail, head = os.path.split(path['suffix'])
        suffixes[head].append({
            'suffix': tail,
            'path': path['path']
        })

    for suffix, values in suffixes.items():
        unique_values = []
        for value in values:
            if value['path'] == value['suffix']:
                output.append(value.values())
            else:
                unique_values.append(value)

        if len(unique_values) == 1:
            short_path = os.path.join(suffix, end) if end else suffix
            output.append([short_path, unique_values.pop()['path']])
            
        else:
            new_end = os.path.join(suffix, end) if end else suffix
            output += _get_unique_suffixes(unique_values, new_end)

    return output

def format_path_for_search(path):
    '''
        Format a string for search

        To make it easier to search a string we format it:
            folder_a/folder_b/filename -->
                filname [folder_a/folder_b/filename]
            or if there are no folders we just return the full path

        This is easier to search because we search left to right.  So if you are looking
        for a file called /foo/bar.py but there are 50 files named bar.py (you don't know this).

        This format:
            bar -> 50 results
            barfoo -> 1 results

        Standard Format:
            bar -> 50 results
            delete search
            foobar -> 1 result
    '''
    tail, head = os.path.split(path)
    if tail and head:
        return "%s [%s]" % (head, os.path.join('..', path))
    if tail:
        return 'Home (%s)' % path
    else:
        return path