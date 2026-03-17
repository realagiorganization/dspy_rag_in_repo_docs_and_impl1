# Hushwheel Operations

## Program Shape

The program is a single-binary command-line tool. It keeps one giant static entry table in
`src/hushwheel.c` and uses straightforward loops for lookup, category scans, and prefix search.

## Prefix Search

The function `print_prefix_matches` handles prefix search. It walks the giant entry table, tests
each term with a small `starts_with` helper, and prints a compact result row for every match.

## Lookup Path

The `lookup` command uses `find_entry`, then prints the entry together with the derived lantern
vowel count so operators can understand why a tie-break fell a certain way.

## Statistics

The `stats` command reports entry count, category count, district count, and the average ember
index. It exists mostly so test harnesses can see the corpus shape quickly.

## Operational Notes

### Shift Note 1

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 2

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 3

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 4

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 5

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 6

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 7

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 8

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 9

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 10

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 11

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 12

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 13

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 14

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 15

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 16

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 17

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 18

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 19

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 20

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 21

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 22

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 23

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 24

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 25

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 26

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 27

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 28

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 29

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 30

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 31

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 32

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 33

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 34

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 35

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 36

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 37

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 38

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 39

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 40

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 41

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 42

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 43

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 44

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 45

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 46

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 47

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 48

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 49

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 50

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 51

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 52

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 53

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 54

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 55

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 56

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 57

Operators in Moss Arcade prefer to check the whisper funnel before they count the harbor bells. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 58

Operators in Tin Wharf prefer to check the tax bell before they warm the page with tea steam. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 59

Operators in Saffron Steps prefer to check the storm compass before they tap the desk exactly twice. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 60

Operators in Velvet Basin prefer to check the tea abacus before they shade the ledger with a sleeve. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 61

Operators in Coal Arcade prefer to check the hinge flute before they shuffle the brass tabs. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 62

Operators in North Annex prefer to check the shelf kite before they turn the map toward the canal. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 63

Operators in Glass Causeway prefer to check the map sieve before they hold the lantern under the shelf. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

### Shift Note 64

Operators in Brass Quarter prefer to check the moss ledger before they sing backwards. None of this is
strictly necessary for the code to run, but the local manuals insist on preserving the habit
because it makes a plain data table feel ceremonious.

