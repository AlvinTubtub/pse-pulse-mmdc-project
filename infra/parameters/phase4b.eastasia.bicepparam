using '../main.bicep'

param location = 'eastasia'
param resourceGroupName = 'rg-pse-pulse-student-prod'
param vmSize = 'Standard_B2als_v2'
param enableSsh = false
param adminSshCidr = ''
param deployBlob = false
param vmAdminUsername = 'psepulseops'
param administratorLogin = 'psepulseadmin'
param postgresVersion = '16'
param postgresSku = 'Standard_B1ms'
