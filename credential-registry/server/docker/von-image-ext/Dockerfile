# TODO: remove the step once a package is available on PyPi
# package pre-requirements
FROM python:3.7-alpine as django-icat-api
WORKDIR /tmp/django-icat-api
ADD django-icat-api .
RUN python setup.py sdist

FROM python:3.7-alpine as python-indy-api
WORKDIR /tmp/python-indy-api
ADD python-indy-api .
RUN python setup.py sdist

# build von-image-ext
FROM bcgovimages/von-image:py36-1.7-ew-0-s2i

COPY --from=django-icat-api /tmp/django-icat-api/dist dist
RUN pip install dist/django-icat-api-0.1.tar.gz

COPY --from=python-indy-api /tmp/python-indy-api/dist dist
RUN pip install dist/python-indy-api-0.1.tar.gz
