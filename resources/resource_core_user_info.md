User is {{ resource_user_data.full_name }}{% if resource_user_data.preferred_name %}, call {{ resource_user_data.pronouns.objective }} {{ resource_user_data.preferred_name }}{% endif %}{% if resource_user_data.birthdate %} (Born: {{ resource_user_data.birthdate }}){% endif %}.

{% if resource_user_data.important_people and resource_user_data.important_people|length > 0 %}
Most important people in {{ resource_user_data.first_name }}'s life:
{% for person in resource_user_data.important_people %}
{{ person.name }}{% if person.relationship %}, {{ person.relationship }}{% endif %}{% if person.birthdate %} (Born: {{ person.birthdate }}){% endif %}.
{% endfor %}
{% endif %}

{% if resource_user_data.job %}
{{ resource_user_data.first_name }} works as {{ resource_user_data.job }}.
{% endif %}

{% if resource_user_data.additional_context %}
General knowledge about {{ resource_user_data.first_name }}:
{{ resource_user_data.additional_context }}
{% endif %}

