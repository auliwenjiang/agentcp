package Locale::Maketext::Simple;
use strict;
use warnings;
sub import {
    my $class = shift;
    my $caller = caller;
    no strict 'refs';
    *{"${caller}::loc"} = sub { return $_[0] };
}
1;
