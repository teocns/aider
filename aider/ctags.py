import os
import json
import sys
import subprocess
import tiktoken

from aider import prompts

# Global cache for tags
TAGS_CACHE = {}

# from aider.dump import dump


def get_tags_map(filenames, root_dname=None):
    if not root_dname:
        root_dname = os.getcwd()

    tags = []
    for filename in filenames:
        if filename.endswith(".md") or filename.endswith(".json"):
            continue
        tags += get_tags(filename, root_dname)
    if not tags:
        return

    tags = sorted(tags)

    output = ""
    last = [None] * len(tags[0])
    tab = "\t"
    for tag in tags:
        tag = list(tag)

        for i in range(len(last)):
            if last[i] != tag[i]:
                break

        num_common = i
        indent = tab * num_common
        rest = tag[num_common:]
        for item in rest:
            output += indent + item + "\n"
            indent += tab
        last = tag

    return output


def split_path(path, root_dname):
    path = os.path.relpath(path, root_dname)
    path_components = path.split(os.sep)
    res = [pc + os.sep for pc in path_components[:-1]]
    res.append(path_components[-1] + ":")
    return res


def get_tags(filename, root_dname):
    # Check if the file is in the cache and if the modification time has not changed
    file_mtime = os.path.getmtime(filename)
    cache_key = (filename, root_dname)
    if cache_key in TAGS_CACHE and TAGS_CACHE[cache_key]["mtime"] == file_mtime:
        return TAGS_CACHE[cache_key]["tags"]

    cmd = ["ctags", "--fields=+S", "--extras=-F", "--output-format=json", filename]
    output = subprocess.check_output(cmd).decode("utf-8")
    output = output.splitlines()

    tags = []
    if not output:
        tags.append(split_path(filename, root_dname))

    for line in output:
        tag = json.loads(line)
        path = tag.get("path")
        scope = tag.get("scope")
        kind = tag.get("kind")
        name = tag.get("name")
        signature = tag.get("signature")

        last = name
        if signature:
            last += " " + signature

        res = split_path(path, root_dname)
        if scope:
            res.append(scope)
        res += [kind, last]
        tags.append(res)

    # Update the cache
    TAGS_CACHE[cache_key] = {"mtime": file_mtime, "tags": tags}

    return tags


class RepoMap:
    use_ctags = False

    def __init__(self, use_ctags, root, main_model):
        self.use_ctags = use_ctags
        self.tokenizer = tiktoken.encoding_for_model(main_model)
        self.root = root

    def get_repo_map(self, chat_files, other_files):
        res = self.choose_files_listing(other_files)
        if not res:
            return

        files_listing, ctags_msg = res

        if chat_files:
            other = "other "
        else:
            other = ""

        repo_content = prompts.repo_content_prefix.format(
            other=other,
            ctags_msg=ctags_msg,
        )
        repo_content += files_listing

        return repo_content

    def choose_files_listing(self, other_files):
        # 1/4 of gpt-4's context window
        max_map_tokens = 2048

        if not other_files:
            return

        if self.use_ctags:
            files_listing = get_tags_map(other_files)
            if self.token_count(files_listing) < max_map_tokens:
                ctags_msg = " with selected ctags info"
                return files_listing, ctags_msg

        files_listing = self.get_simple_files_map(other_files)
        ctags_msg = ""
        if self.token_count(files_listing) < max_map_tokens:
            return files_listing, ctags_msg

    def get_simple_files_map(self, other_files):
        files_listing = "\n".join(self.get_rel_fname(ofn) for ofn in sorted(other_files))
        return files_listing

    def token_count(self, string):
        return len(self.tokenizer.encode(string))

    def get_rel_fname(self, fname):
        return os.path.relpath(fname, self.root)


if __name__ == "__main__":
    res = get_tags_map(sys.argv[1:])
    print(res)
