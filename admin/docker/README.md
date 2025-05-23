Our docker images. Note that images depend on each other, please use the script
admin/update_docker.sh to build images in the correct order.

We have 4 images which are only used locally in the build process, and are not
uploaded to a repository. 
 - `runreqs`: Base image containing just the things needed to run problemtools
 - `build`: Base image containing just the things needed to build a deb and run problemtools
 - `icpclangs`: Base image containing what is needed to run problemtools, plus the "ICPC languages"
 - `fulllangs`: Base image containing what is needed to run problemtools, plus all supported languages

We have 3 images which are meant for end users:
 - `minimal`: Image with problemtools installed, but no languages.
 - `icpc`: Image with problemtools plus the "ICPC languages" installed.
 - `full`: Image with problemtools and all languages

We have 1 image which is used in our CI (to speed up things - it takes a few
minutes to apt-get install all languages and runtime requirements):
 - `githubci`: Image with all languages and everything needed to build a deb and run problemtools

Build dependencies:
```
     runreqs   -> icpclangs -> fullangs -> githubci
     /     \          |           |
 build    minimal    icpc        full
```
