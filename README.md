### Edifice

This project links several Chicago building and property datasets. In particular:

* City of Chicago Building Footprints
* Cook County Address Points (used as a canonical list of addresses)
* Cook County Tax Assessor's Office FOIA Request 22606 (property tax assessment records for 2013)

To retrieve, transform, and load the data,

1. In the root of this repository, run `cp config.mk.example config.mk` 
   to create a configuration file for Make, and adjust the database 
   environment variables to match your system.
2. Type `make` at the command line to build all targets in the `Makefile`.
   This will create a table called `edifice` with the combined datasets. 

### Notes

If you see errors about missing dependencies, you'll want to check first that you have all of the system dependencies installed. This project requires postgres, python, pip, and virtualenv. An example setup script is included in [./setup.sh.example] for Ubuntu 14.04. If you wish to use this script, you will need to tweak it for your system.

### Acknowledgments

This project takes its name from the [Edifice project](http://edifice.opencityapps.org/) by @jpvelez, which visualized datasets holding information on Chicago's built environment. Many thanks to the team at @datamade for their work on @dedupe and @usaddress, which are used here to match records from different datasets, and the excellent examples they've put together.

### License
Copyright (c) 2015, Justin Manley. Released under the [MIT license](./LICENSE).
