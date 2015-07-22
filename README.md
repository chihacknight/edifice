### Edifice

This repository provides code for joining several building / property datasets from the City of Chicago and Cook County, IL. In particular:
* City of Chicago Building Footprints
* Cook County Address Points (used as a canonical list of addresses)
* Cook County Parcels
* Cook County Tax Assessor's Office FOIA Request 22606 (property tax assessment records for 2013)

To retrieve, transform, and load the data,

1. In the root of this repository, run `cp config.mk.example config.mk` 
   to create a configuration file for Make, and adjust the database 
   environment variables to match your system.
2. Run `virtualenv . && source bin/activate && pip install -r requirements.txt` to create an isolated python environment and install the project's python dependencies.
3. Type `make` at the command line to build all targets in the `Makefile`.

### Acknowledgments

This project takes its name from the [Edifice project](http://edifice.opencityapps.org/) by @jpvelez, which visualized datasets holding information on Chicago's built environment. 

### License
