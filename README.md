# eao-evidence-locker
Ensure genuine inspection reports by using blockchain technology

To build/run this application, do the following:

You need an Indy ledger - clone, build and run von-network:

```bash
git clone https://github.com/bcgov/von-network.git
cd von-network
./manage build
./manage run --logs
```

Open a second bash shell and clone the EAO demo repository:

```bash
git clone https://github.com/bcgov/eao-inspections-evidence-locker.git
cd eao-inspections-evidence-locker
```

In the same bash shell, build the credential registry (note you need to specify a THEME to build):

```bash
cd starter-kit/credential-registry/docker
TOB_THEME_PATH=/Users/icostanzo/Reference/eao-inspections-evidence-locker/starter-kit/credential-registry/client/tob-web/themes/ TOB_THEME=bcgov ./manage build
```

(Note - substitute your local directory name.)

Open a third bash shell and build the issuer agent:

```bash
cd starter-kit/agent/docker
./manage build
```

Once the dockers are fnished building, in the *second* shell start the credental registry (note you need to specify the THEME):

```bash
TOB_THEME=bcgov ./manage start seed=my_seed_000000000000000000000000
```

Once the credential registry is running, in the *third shell* start the EAO issuer:

```bash
./manage start
```

To load data see the instrutions here:  starter-kit/agent/eao-pipeline

You can run the jobs through the mara console (http://localhost:5050), however you need a connection to the EAO source mongodb.
