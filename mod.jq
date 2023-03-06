if ."urn:mace:oclc.org:eidm:schema:persona:notifications:20180509".selfAssertedEmail then
."urn:mace:oclc.org:eidm:schema:persona:notifications:20180509".selfAssertedEmail 
    |= sub("dominiovecchio.it";"nuovodominio.it")
else 
    .
end
| .emails[].value |=
sub("dominiovecchio.it";"nuovodominio.it")
